"""OME-524 — headless full-flow e2e for the compose smoke (spec §11; docs/protocol.md §8).

The docker-compose e2e (NATS + App + mock-runner) needs live infra, so this is its headless
twin: the real ``create_app`` App, an :class:`InMemoryBus`, and a fake ``JobRunner`` that stands in
for the scheduled Runner by publishing the §8 mock stream. Drives the whole contract —
``POST /token → open WS → GET /?q= → stream → DELETE → purge`` — asserting every streamed frame
validates through :data:`OutboundFrameAdapter` and satisfies §8 (roll-up + ordering + sequence).
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.jobs.port import JobStatus, job_name
from url4_cloud.testing.mock_runner import publish_mock_run
from url4_cloud_nats import InMemoryBus
from url4_streaming_protocol import (
    AttachData,
    AttachEvent,
    CostUsageEvent,
    OutboundFrame,
    OutboundFrameAdapter,
    ResultEvent,
    SpanEvent,
    TerminatedEvent,
)

SECRET = "e2e-secret"
WINDOW_S = 60
SUBPROTOCOL = "cloudevents.json"
EXPR = "(gpt,claude)!'hi'"
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)


class MockRunnerJobRunner:
    """A fake ``JobRunner`` that 'runs the container' by publishing the §8 mock stream to the bus.

    Mirrors what a scheduled Runner does — schedule ⇒ a runner starts emitting frames —
    but in-process against the injected :class:`InMemoryBus`, so the e2e needs no Docker/NATS.
    """

    def __init__(self, bus: InMemoryBus) -> None:
        self._bus = bus
        self.scheduled: list[tuple[str, str, int]] = []
        self.stopped: list[str] = []
        self._tasks: list[asyncio.Task[None]] = []

    def schedule(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
    ) -> str:
        self.scheduled.append((topic, url4, deadline_s))
        # WHY: schedule() is sync (the port), but it runs inside the async GET handler, so a running
        # loop exists — spawn the publish as a background task, the container stand-in.
        self._tasks.append(asyncio.ensure_future(publish_mock_run(self._bus, topic, url4)))
        return job_name(topic)

    def stop(self, topic: str) -> None:
        self.stopped.append(topic)

    def exists(self, topic: str) -> bool:
        return False

    def status(self, topic: str) -> JobStatus:
        return "running"


def _make_app(bus: InMemoryBus, runner: MockRunnerJobRunner) -> FastAPI:
    # ws_heartbeat_s high so no heartbeat interleaves the 11 data frames.
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S, ws_heartbeat_s=30.0)
    return create_app(settings, bus=bus, job_runner=runner, clock=lambda: T0)


def _topic_of(token: str) -> str:
    return str(JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).verify(token, T0)["sub"])


def _attach() -> dict[str, Any]:
    return AttachEvent(
        id="att", source="/client", subject="t", data=AttachData(from_sequence=None)
    ).model_dump(mode="json", by_alias=True)


def _read_until_terminated(ws: Any) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for _ in range(40):
        frame = ws.receive_json()
        frames.append(frame)
        if frame["type"] == "ai.url4.terminated":
            return frames
    raise AssertionError("no terminated frame within the read budget")


def _span_parent(event: SpanEvent) -> str | None:
    return None if event.tracestate is None else event.tracestate.split("=", 1)[1]


def test_full_flow_streams_valid_section8_events_then_purges() -> None:
    bus = InMemoryBus()
    runner = MockRunnerJobRunner(bus)
    app = _make_app(bus, runner)
    with TestClient(app) as client:
        token = client.post("/token").json()["token"]
        topic = _topic_of(token)
        cap = {"URL4-Capability": token}

        with client.websocket_connect(f"/ws?ticket={token}", subprotocols=[SUBPROTOCOL]) as ws:
            ws.send_json(_attach())
            started = client.get(
                "/", params={"q": EXPR}, headers={**cap, "Prefer": "respond-async"}
            )
            assert started.status_code == 202
            assert runner.scheduled and runner.scheduled[0][0] == topic
            wire = _read_until_terminated(ws)

            # Every streamed frame validates through the discriminated wire adapter (spec §11/§12).
            frames: list[OutboundFrame] = [OutboundFrameAdapter.validate_python(f) for f in wire]
            assert [f.type for f in frames][0] == "ai.url4.started"
            assert isinstance(frames[-1], TerminatedEvent)
            assert frames[-1].data.status == "succeeded"
            # Monotonic, gapless sequence the App relayed from the stream (docs/protocol.md §6).
            assert [int(f.sequence) for f in frames if f.sequence is not None] == list(
                range(1, len(frames) + 1)
            )
            _assert_cost_rolls_up(frames)
            _assert_span_tree(frames)

            purged = client.delete("/", params={"topic": topic}, headers=cap)
        assert purged.status_code == 204
    assert runner.stopped == [topic]
    assert bus._log[topic] == []  # noqa: SLF001 — asserting the DELETE purge side effect


def _assert_cost_rolls_up(frames: list[OutboundFrame]) -> None:
    costs = [f for f in frames if isinstance(f, CostUsageEvent)]
    selfs = [c for c in costs if c.data.scope == "self"]
    subtree = next(c for c in costs if c.data.scope == "subtree")
    # §8: subtree.total == self + Σ children.self.
    assert subtree.data.cost.total_usd == sum((c.data.cost.total_usd for c in selfs), Decimal("0"))
    # §8 ordering: CostUsage{subtree} precedes Result.
    subtree_idx = frames.index(subtree)
    result_idx = next(i for i, f in enumerate(frames) if isinstance(f, ResultEvent))
    assert subtree_idx < result_idx


def _assert_span_tree(frames: list[OutboundFrame]) -> None:
    spans = [f for f in frames if isinstance(f, SpanEvent)]
    seen: set[str] = set()
    for span in spans:
        assert span.traceparent is not None
        parent = _span_parent(span)
        if parent is not None:
            assert parent in seen  # §8: parent refers to an already-emitted span
        seen.add(span.traceparent.split("-")[2])
    assert len(seen) == len(spans)
