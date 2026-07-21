"""Behaviour tests for the url4-cloud WebSocket bridge (OME-521; spec §6, docs/protocol.md §8).

Headless: an :class:`InMemoryBus` and a fake ``JobRunner`` are injected via ``create_app`` — no
live NATS/k8s. The bus is seeded through the ``TestClient`` blocking portal so its per-topic
condition binds to the same event loop the ASGI app (and thus the WS endpoint) runs on.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.jobs.port import JobStatus, job_name
from url4_cloud.rest import DenyAllGate
from url4_cloud.ws import ConnectionRegistry
from url4_cloud_nats import InMemoryBus
from url4_streaming_protocol import (
    AttachData,
    AttachEvent,
    CostBreakdown,
    CostUsageData,
    CostUsageEvent,
    OutboundFrame,
    StartedData,
    StartedEvent,
    StopData,
    StopEvent,
    TerminatedData,
    TerminatedEvent,
    TokenUsage,
)

SECRET = "ws-unit-secret"
WINDOW_S = 60
SUBPROTOCOL = "cloudevents.json"
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)


# --- fakes ----------------------------------------------------------------


class FakeJobRunner:
    """A headless ``JobRunner`` that records stops (the WS ``StopEvent`` side effect)."""

    def __init__(self) -> None:
        self.stopped: list[str] = []
        self.scheduled: list[tuple[str, str, int]] = []

    def schedule(self, topic: str, url4: str, deadline_s: int) -> str:
        self.scheduled.append((topic, url4, deadline_s))
        return job_name(topic)

    def stop(self, topic: str) -> None:
        self.stopped.append(topic)

    def exists(self, topic: str) -> bool:
        return False

    def status(self, topic: str) -> JobStatus:
        return "running"


# --- helpers --------------------------------------------------------------


def _token(topic: str) -> str:
    return JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)


def _make_app(
    *,
    bus: InMemoryBus | None,
    job_runner: FakeJobRunner | None = None,
    ws_heartbeat_s: float = 30.0,
) -> FastAPI:
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S, ws_heartbeat_s=ws_heartbeat_s)
    return create_app(
        settings,
        bus=bus,
        job_runner=job_runner or FakeJobRunner(),
        clock=lambda: T0,
    )


def _seed(client: TestClient, bus: InMemoryBus, topic: str, events: list[OutboundFrame]) -> None:
    # WHY: publish on the app's event loop (via the portal) so the bus condition binds there.
    portal = client.portal
    assert portal is not None
    for event in events:
        portal.call(bus.publish, topic, event)


def _attach(from_sequence: int | None) -> dict[str, Any]:
    event = AttachEvent(
        id="att", source="/client", subject="t", data=AttachData(from_sequence=from_sequence)
    )
    return event.model_dump(mode="json", by_alias=True)


def _stop() -> dict[str, Any]:
    return StopEvent(id="stp", source="/client", subject="t", data=StopData()).model_dump(
        mode="json", by_alias=True
    )


def _started(topic: str) -> StartedEvent:
    return StartedEvent(
        id=f"s-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=StartedData(url4="gpt()"),
    )


def _cost(topic: str) -> CostUsageEvent:
    return CostUsageEvent(
        id=f"c-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=CostUsageData(
            scope="self",
            provider="anthropic",
            model="claude-opus-4-8",
            pricing_version="2026-07-01",
            usage=TokenUsage(input_tokens=1200, output_tokens=340),
            cost=CostBreakdown(
                input_usd=Decimal("0.0180"),
                output_usd=Decimal("0.0255"),
                total_usd=Decimal("0.0435"),
            ),
        ),
    )


def _terminated(topic: str) -> TerminatedEvent:
    return TerminatedEvent(
        id=f"t-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=TerminatedData(status="succeeded"),
    )


# --- streaming ------------------------------------------------------------


def test_ws_streams_published_events_in_order_as_cloudevents_json() -> None:
    topic = "ws-order"
    bus = InMemoryBus()
    app = _make_app(bus=bus)
    with TestClient(app) as client:
        _seed(client, bus, topic, [_started(topic), _cost(topic), _terminated(topic)])
        url = f"/ws?ticket={_token(topic)}"
        with client.websocket_connect(url, subprotocols=[SUBPROTOCOL]) as ws:
            ws.send_json(_attach(None))
            frames = [ws.receive_json() for _ in range(3)]
    types = [f["type"] for f in frames]
    assert types == ["ai.url4.started", "ai.url4.cost.usage", "ai.url4.terminated"]
    assert [f["sequence"] for f in frames] == ["1", "2", "3"]
    assert all(f["specversion"] == "1.0" for f in frames)
    # by_alias: the OTel gen_ai.* keys survive to the wire.
    assert frames[1]["data"]["gen_ai.provider.name"] == "anthropic"
    assert frames[1]["data"]["cost"]["total_usd"] == "0.0435"


def test_ws_attach_from_sequence_replays_the_gap() -> None:
    topic = "ws-resume"
    bus = InMemoryBus()
    app = _make_app(bus=bus)
    with TestClient(app) as client:
        _seed(client, bus, topic, [_started(topic), _cost(topic), _terminated(topic)])
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_attach(2))
            frames = [ws.receive_json() for _ in range(2)]
    assert [f["sequence"] for f in frames] == ["2", "3"]
    assert [f["type"] for f in frames] == ["ai.url4.cost.usage", "ai.url4.terminated"]


def test_ws_heartbeat_on_idle_connection() -> None:
    topic = "ws-heartbeat"
    bus = InMemoryBus()
    app = _make_app(bus=bus, ws_heartbeat_s=0.05)
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            frame = ws.receive_json()
    assert frame["type"] == "ai.url4.heartbeat"
    assert frame["subject"] == topic


def test_ws_stop_event_stops_the_job() -> None:
    topic = "ws-stop"
    bus = InMemoryBus()
    runner = FakeJobRunner()
    app = _make_app(bus=bus, job_runner=runner, ws_heartbeat_s=0.05)
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_stop())
            # A heartbeat proves the inbound Stop was consumed and the socket is still live.
            assert ws.receive_json()["type"] == "ai.url4.heartbeat"
    assert runner.stopped == [topic]


def test_ws_reattach_cancels_prior_subscription_and_replays() -> None:
    # A second Attach re-subscribes (reconnect/resume): the prior pump is cancelled and the
    # stream replays from the requested point. One seeded frame ⇒ the replay is deterministic.
    topic = "ws-reattach"
    bus = InMemoryBus()
    app = _make_app(bus=bus)
    with TestClient(app) as client:
        _seed(client, bus, topic, [_started(topic)])
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_attach(None))
            first = ws.receive_json()
            ws.send_json(_attach(1))
            second = ws.receive_json()
    assert first["sequence"] == "1"
    assert second["sequence"] == "1"
    assert second["type"] == "ai.url4.started"


def test_ws_ignores_malformed_inbound_frames() -> None:
    # Non-JSON text and a well-formed-but-unknown frame are dropped, not fatal: the socket lives.
    topic = "ws-malformed"
    bus = InMemoryBus()
    app = _make_app(bus=bus, ws_heartbeat_s=0.05)
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_text("this is not json {{{")
            ws.send_json({"type": "ai.url4.bogus", "id": "x", "source": "/c"})
            assert ws.receive_json()["type"] == "ai.url4.heartbeat"


# --- rejection paths ------------------------------------------------------


def test_ws_invalid_ticket_is_rejected() -> None:
    app = _make_app(bus=InMemoryBus())
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws?ticket=not-a-jwt") as ws:
                ws.receive_json()


def test_ws_missing_ticket_is_rejected() -> None:
    app = _make_app(bus=InMemoryBus())
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()


def test_ws_without_bus_is_rejected() -> None:
    app = _make_app(bus=None)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws?ticket={_token('no-bus')}") as ws:
                ws.receive_json()


# --- interest gate: a live WS flips the REST 428 (spec §2.1/§4) ------------


def test_live_ws_enables_start_and_closing_it_restores_428() -> None:
    topic = "ws-gate"
    bus = InMemoryBus()
    runner = FakeJobRunner()
    app = _make_app(bus=bus, job_runner=runner)
    headers = {"Authorization": f"Bearer {_token(topic)}"}
    with TestClient(app) as client:
        before = client.get("/", params={"q": "gpt()"}, headers=headers)
        assert before.status_code == 428
        url = f"/ws?ticket={_token(topic)}"
        with client.websocket_connect(url, subprotocols=[SUBPROTOCOL]) as ws:
            ws.send_json(_attach(None))
            during = client.get(
                "/", params={"q": "gpt()"}, headers={**headers, "Prefer": "respond-async"}
            )
        assert during.status_code == 202
        after = client.get("/", params={"q": "gpt()"}, headers=headers)
    assert after.status_code == 428
    assert runner.scheduled and runner.scheduled[0][0] == topic


# --- registry + default gate ----------------------------------------------


@pytest.mark.asyncio
async def test_connection_registry_counts_live_subscribers() -> None:
    registry = ConnectionRegistry()
    assert await registry.has_subscriber("t") is False
    registry.add("t")
    registry.add("t")
    assert await registry.has_subscriber("t") is True
    registry.remove("t")
    assert await registry.has_subscriber("t") is True
    registry.remove("t")
    assert await registry.has_subscriber("t") is False
    # Removing an unknown topic is a harmless no-op.
    registry.remove("t")
    assert await registry.has_subscriber("t") is False


@pytest.mark.asyncio
async def test_deny_all_gate_reports_no_subscriber() -> None:
    assert await DenyAllGate().has_subscriber("anything") is False
