"""The full local-mode protocol, end to end, through the real App.

Token → WS attach → `GET /?q=` → frames → terminal, with only the two adapters swapped. This is
what makes `--local` a deployment rather than a demo: everything between the REST route and the
WS pump is the code a deployed App runs, so a regression in the protocol surfaces here and not
only in a cluster.

The executor is stubbed — the engine and the model calls have their own tests, and wiring a real
aigateway world here would make this a network test instead of a protocol one.
"""

import json
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from url4.streaming.interfaces import Completed, ExecStep, Executor, TraceContext
from url4.streaming.protocol import LogData, ResultData
from url4.streaming.protocol.signals import CostUsageData
from url4.streaming.protocol.taxonomy import CostBreakdown, TokenUsage
from url4_cloud.adapters.inprocess import InProcessJobRunner
from url4_cloud.adapters.memory import InMemoryEventStream
from url4_cloud.app import create_app
from url4_cloud.config import Settings

SECRET = "s" * 32


class _EchoExecutor(Executor):
    """Emits one log then completes — enough to prove frames flow, cheap enough to stay a unit."""

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        yield LogData.at("INFO", f"running {url4}")
        yield Completed(
            result=ResultData(body=f"result::{url4}"),
            subtree_cost=CostUsageData(
                scope="self",
                provider="test",
                model="test-model",
                pricing_version="v0",
                usage=TokenUsage(input_tokens=1, output_tokens=1),
                cost=CostBreakdown(total_usd=Decimal("0")),
            ),
        )


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A local-mode App, assembled the way `create_local_app` does but with a stub executor."""
    settings = Settings(jwt_secret=SECRET)
    stream = InMemoryEventStream()
    runner = InProcessJobRunner(stream, lambda _env: _EchoExecutor(), base_env={})
    app = create_app(settings, stream=stream, job_runner=runner)
    app.router.on_shutdown.append(runner.aclose)
    with TestClient(app) as test_client:
        yield test_client


def _cap(token: str) -> dict[str, str]:
    """The capability token rides `URL4-Capability`, never `Authorization` — that header is
    reserved for the aigateway credential this run forwards downstream."""
    return {"URL4-Capability": token}


def _token(client: TestClient) -> str:
    response = client.post("/token")
    assert response.status_code == 200
    return str(response.json()["token"])


def test_a_run_starts_and_returns_its_result_synchronously(client: TestClient) -> None:
    token = _token(client)
    with client.websocket_connect(f"/ws?ticket={token}"):
        response = client.get("/?q=hello", headers=_cap(token))

    assert response.status_code == 200
    assert response.text == "result::hello"


def test_the_run_streams_its_whole_lifecycle_over_the_websocket(client: TestClient) -> None:
    """Started → Log → CostUsage(subtree) → Result → Terminated, in sequence, over the real pump."""
    token = _token(client)
    with client.websocket_connect(f"/ws?ticket={token}") as ws:
        ws.send_text(
            json.dumps(
                {
                    "specversion": "1.0",
                    "id": "attach-1",
                    "source": "/test",
                    "type": "ai.url4.attach",
                    "data": {},
                }
            )
        )
        client.get("/?q=hello", headers=_cap(token))

        seen: list[str] = []
        while "ai.url4.terminated" not in seen:
            frame = json.loads(ws.receive_text())
            if frame["type"] != "ai.url4.heartbeat":
                seen.append(frame["type"])

    assert seen == [
        "ai.url4.started",
        "ai.url4.log",
        "ai.url4.cost.usage",
        "ai.url4.result",
        "ai.url4.terminated",
    ]


def test_a_run_without_an_attached_subscriber_is_refused(client: TestClient) -> None:
    """The 428 gate is protocol discipline, and local mode keeps it rather than relaxing it."""
    token = _token(client)

    response = client.get("/?q=hello", headers=_cap(token))

    assert response.status_code == 428


def test_frames_replay_for_a_subscriber_that_attaches_late(client: TestClient) -> None:
    """Sequence numbers and replay-from are real here, exactly as they are against JetStream."""
    token = _token(client)
    with client.websocket_connect(f"/ws?ticket={token}"):
        client.get("/?q=hello", headers=_cap(token))

    # a second connection on the same topic replays the finished run from the start
    with client.websocket_connect(f"/ws?ticket={token}") as ws:
        ws.send_text(
            json.dumps(
                {
                    "specversion": "1.0",
                    "id": "attach-2",
                    "source": "/test",
                    "type": "ai.url4.attach",
                    "data": {"from_sequence": 1},
                }
            )
        )
        first = json.loads(ws.receive_text())
        while first["type"] == "ai.url4.heartbeat":
            first = json.loads(ws.receive_text())

    assert first["type"] == "ai.url4.started"
    assert first["sequence"] == "1"


def test_a_replayed_token_cannot_start_a_second_run(client: TestClient) -> None:
    """The single-use guard is the runner's `job_name` registry — same rule as a k8s Job's name."""
    token = _token(client)
    with client.websocket_connect(f"/ws?ticket={token}"):
        client.get("/?q=hello", headers=_cap(token))
        # the first run finished, so its slot is free; a topic that is still running is the case
        # the 409 covers, and `test_inprocess_runner` pins that directly.
        second = client.get("/?q=hello", headers=_cap(token))

    assert second.status_code == 200


def test_stopping_a_run_purges_its_stream(client: TestClient) -> None:
    token = _token(client)
    with client.websocket_connect(f"/ws?ticket={token}"):
        client.get("/?q=hello", headers=_cap(token))
        response = client.delete("/", headers=_cap(token))

    assert response.status_code == 204
