"""``url4-cloud local`` end-to-end spine (local-mode PRD §7 tests 4-6/9,
docs/plans/url4-cloud-integration/prd/local-mode.md).

Headless but real: ``make_local_app`` wires a real :class:`InMemoryBus` +
:class:`InProcessJobRunner` driving a real :class:`Url4Executor` over a deny-by-default
:class:`StaticIOLayer` world (no network). WS harness reused verbatim from ``test_ws.py``
(``TestClient`` + its blocking portal so REST and WS calls share the app's event loop).
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from url4.io.static import StaticIOLayer

from url4_cloud.app import make_local_app
from url4_cloud.jobs.inprocess import InProcessJobRunner
from url4_cloud_runner.aigateway_connector import (
    AigatewayConfig,
    AigatewayWorld,
    build_aigateway_world,
)
from url4_cloud_runner.executor import ExecStep, TraceContext
from url4_cloud_runner.url4_executor import Url4Executor
from url4_streaming_protocol import AttachData, AttachEvent

SUBPROTOCOL = "cloudevents.json"
_MODEL_EXPR = "/claude-haiku-4-5(ctx)!'summarize'"


def _attach(from_sequence: int | None) -> dict[str, Any]:
    event = AttachEvent(
        id="att", source="/client", subject="t", data=AttachData(from_sequence=from_sequence)
    )
    return event.model_dump(mode="json", by_alias=True)


class _BlockingExecutor:
    """Yields nothing; blocks on an ``Event`` that's never set — a pending in-flight run
    (mirrors ``tests/unit/test_jobs_inprocess.py``'s fixture, reused here for the integration
    graceful-shutdown/max-runs scenarios which need it at the app-factory level)."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.resumed = False
        self.gate = asyncio.Event()

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        self.started.set()
        await self.gate.wait()
        self.resumed = True
        if False:  # pragma: no cover - never reached; keeps this an async generator function
            yield


async def _wait_started(started: asyncio.Event) -> None:
    await asyncio.wait_for(started.wait(), timeout=2.0)


async def _release_and_wait_free(gate: asyncio.Event, runner: InProcessJobRunner) -> None:
    gate.set()

    async def _poll() -> None:
        while runner.active_count() > 0:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout=2.0)


# --- PRD test 5: the spine — full happy path over the real local app ---------------------------


def test_local_spine_full_happy_path_streams_frames_in_order() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    app = make_local_app(executor_factory=lambda: Url4Executor(io))
    with TestClient(app) as client:
        token = client.post("/token").json()["token"]
        headers = {"URL4-Capability": token}
        url = f"/ws?ticket={token}"
        with client.websocket_connect(url, subprotocols=[SUBPROTOCOL]) as ws:
            ws.send_json(_attach(None))
            resp = client.get("/", params={"q": "https://a!go"}, headers=headers)
            frames = []
            while True:
                frame = ws.receive_json()
                frames.append(frame)
                if frame["type"] == "ai.url4.terminated":
                    break

    assert resp.status_code == 200
    types = [f["type"] for f in frames]
    assert types[0] == "ai.url4.started"
    assert types[-1] == "ai.url4.terminated"
    assert "ai.url4.result" in types
    assert frames[-1]["data"]["status"] == "succeeded"
    # sequence is monotonic starting at 1, matching the JetStream contract.
    assert [f["sequence"] for f in frames] == [str(i) for i in range(1, len(frames) + 1)]


# --- PRD test 6: resume parity — disconnect after frame 3, reattach, replay the gap -------------


def test_local_spine_resume_parity_replays_the_gap_after_reconnect() -> None:
    io = StaticIOLayer(fetch_map={"https://x": "X", "https://y": "Y"})
    app = make_local_app(executor_factory=lambda: Url4Executor(io))
    with TestClient(app) as client:
        token = client.post("/token").json()["token"]
        headers = {"URL4-Capability": token}
        url = f"/ws?ticket={token}"
        with client.websocket_connect(url, subprotocols=[SUBPROTOCOL]) as ws:
            ws.send_json(_attach(None))
            resp = client.get(
                "/",
                params={"q": "(https://x, https://y)!go"},
                headers={**headers, "Prefer": "respond-async"},
            )
            assert resp.status_code == 202
            first_batch = [ws.receive_json() for _ in range(3)]
        # WS #1 is now disconnected; the run keeps executing independently of the connection.
        assert [f["sequence"] for f in first_batch] == ["1", "2", "3"]

        with client.websocket_connect(url, subprotocols=[SUBPROTOCOL]) as ws2:
            ws2.send_json(_attach(4))
            rest = []
            while True:
                frame = ws2.receive_json()
                rest.append(frame)
                if frame["type"] == "ai.url4.terminated":
                    break

    assert rest[0]["sequence"] == "4"
    assert rest[-1]["type"] == "ai.url4.terminated"
    assert rest[-1]["data"]["status"] == "succeeded"


# --- PRD test 4: graceful shutdown cancels an in-flight run cleanly -----------------------------


@pytest.mark.filterwarnings("error")
def test_local_app_graceful_shutdown_cancels_in_flight_runs() -> None:
    blocking = _BlockingExecutor()
    app = make_local_app(executor_factory=lambda: blocking)
    with TestClient(app) as client:
        token = client.post("/token").json()["token"]
        headers = {"URL4-Capability": token}
        with client.websocket_connect(f"/ws?ticket={token}", subprotocols=[SUBPROTOCOL]) as ws:
            ws.send_json(_attach(None))
            resp = client.get(
                "/", params={"q": "gpt()"}, headers={**headers, "Prefer": "respond-async"}
            )
            assert resp.status_code == 202
            portal = client.portal
            assert portal is not None
            portal.call(_wait_started, blocking.started)
        # `with TestClient(...)` exit runs the ASGI lifespan shutdown, which calls
        # `runner.aclose()` (wired by `make_local_app`) — the blocking task must be cancelled.
    assert blocking.resumed is False


# --- PRD test 9: max-runs admission gate ---------------------------------------------------------


def test_local_app_max_runs_gate_returns_503_at_capacity_then_frees_after_release() -> None:
    blocking = _BlockingExecutor()
    app = make_local_app(max_runs=1, executor_factory=lambda: blocking)
    with TestClient(app) as client:
        token_a = client.post("/token").json()["token"]
        token_b = client.post("/token").json()["token"]
        token_c = client.post("/token").json()["token"]
        portal = client.portal
        assert portal is not None

        with client.websocket_connect(f"/ws?ticket={token_a}", subprotocols=[SUBPROTOCOL]) as ws_a:
            ws_a.send_json(_attach(None))
            first = client.get(
                "/",
                params={"q": "gpt()"},
                headers={"URL4-Capability": token_a, "Prefer": "respond-async"},
            )
            assert first.status_code == 202
            portal.call(_wait_started, blocking.started)

            with client.websocket_connect(
                f"/ws?ticket={token_b}", subprotocols=[SUBPROTOCOL]
            ) as ws_b:
                ws_b.send_json(_attach(None))
                second = client.get(
                    "/",
                    params={"q": "gpt()"},
                    headers={"URL4-Capability": token_b, "Prefer": "respond-async"},
                )
            assert second.status_code == 503
            assert second.headers["content-type"].startswith("application/problem+json")

            portal.call(_release_and_wait_free, blocking.gate, app.state.job_runner)

        with client.websocket_connect(f"/ws?ticket={token_c}", subprotocols=[SUBPROTOCOL]) as ws_c:
            ws_c.send_json(_attach(None))
            third = client.get(
                "/",
                params={"q": "gpt()"},
                headers={"URL4-Capability": token_c, "Prefer": "respond-async"},
            )
    assert third.status_code == 202


# --- aigateway connector integration spine (D2 plan, Batch 4 payoff) ---------------------------


def _stub_aigateway_handler(seen_auth: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    """A minimal stubbed aigateway: every completion call succeeds with real-looking usage,
    recording the ``Authorization`` header it was called with (the local-mode credential-scope
    guard needs to prove which token actually reached aigateway)."""

    def handle(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("authorization", ""))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "SUMMARY"}}],
                "usage": {"prompt_tokens": 42, "completion_tokens": 13, "total_tokens": 55},
            },
        )

    return handle


def _build_stub_world(*, token: str, seen_auth: list[str]) -> AigatewayWorld:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_stub_aigateway_handler(seen_auth)), base_url="http://aigw"
    )
    cfg = AigatewayConfig(models=("claude-haiku-4-5",))
    return asyncio.run(build_aigateway_world(cfg, token=token, client=client))


def _run_model_expr_over_ws(
    app: FastAPI, headers: dict[str, str]
) -> tuple[int, list[dict[str, Any]]]:
    """Drive the local spine's REST+WS dance for ``_MODEL_EXPR``: token -> WS attach ->
    ``GET /?q=`` -> collect frames through ``Terminated`` — the harness every spine test shares."""
    with TestClient(app) as client:
        token = client.post("/token").json()["token"]
        ws_headers = {"URL4-Capability": token, **headers}
        url = f"/ws?ticket={token}"
        with client.websocket_connect(url, subprotocols=[SUBPROTOCOL]) as ws:
            ws.send_json(_attach(None))
            resp = client.get("/", params={"q": _MODEL_EXPR}, headers=ws_headers)
            frames = []
            while True:
                frame = ws.receive_json()
                frames.append(frame)
                if frame["type"] == "ai.url4.terminated":
                    break
    return resp.status_code, frames


def test_local_spine_aigateway_real_model_call_streams_real_usage_end_to_end() -> None:
    # Headless but real, per the aigateway connector plan (docs/plans/aigateway-connector/plan.md
    # §7 Batch 4): the shared world is a real Url4Node driven by the real engine, only aigateway
    # itself is stubbed (httpx.MockTransport) — proving engine sink -> adapter roll-up -> wire.
    seen_auth: list[str] = []
    world = _build_stub_world(token="tok", seen_auth=seen_auth)
    app = make_local_app(aigateway=world)

    status_code, frames = _run_model_expr_over_ws(app, {})

    assert status_code == 200
    types = [f["type"] for f in frames]
    assert types[0] == "ai.url4.started"
    assert types[-1] == "ai.url4.terminated"
    assert frames[-1]["data"]["status"] == "succeeded"

    result_idx = types.index("ai.url4.result")
    terminated_idx = types.index("ai.url4.terminated")
    usage_idxs = [i for i, t in enumerate(types) if t == "ai.url4.cost.usage"]
    assert len(usage_idxs) == 2  # §8: CostUsage{self} then CostUsage{subtree}
    self_idx, subtree_idx = usage_idxs
    assert self_idx < subtree_idx < result_idx < terminated_idx
    assert frames[self_idx]["data"]["scope"] == "self"
    assert frames[subtree_idx]["data"]["scope"] == "subtree"

    result_frame = frames[result_idx]
    assert "SUMMARY" in result_frame["data"]["body"]

    # THE payoff: real (stubbed) token usage reached the wire through the engine's usage sink.
    self_usage = frames[self_idx]["data"]
    assert self_usage["usage"]["gen_ai.usage.input_tokens"] == 42
    assert self_usage["usage"]["gen_ai.usage.output_tokens"] == 13
    assert self_usage["pricing_version"] == "unpriced"
    assert self_usage["cost"]["total_usd"] == "0"

    assert seen_auth == ["Bearer tok"]


def test_local_mode_ignores_the_forwarded_per_run_aigateway_credential() -> None:
    # Local-mode credential model (plan §Design decision dec:A, Batch 4): a single process-level
    # aigateway credential backs ONE shared world; the per-run `Authorization` header routes.py
    # forwards into `schedule(credential=)` is a documented no-op locally — the completion call
    # must still authenticate with the SHARED world's build-time token, never the forwarded one.
    seen_auth: list[str] = []
    world = _build_stub_world(token="process-token", seen_auth=seen_auth)
    app = make_local_app(aigateway=world)

    status_code, frames = _run_model_expr_over_ws(app, {"Authorization": "Bearer other-token"})

    assert status_code == 200
    assert frames[-1]["data"]["status"] == "succeeded"
    assert seen_auth == ["Bearer process-token"]
