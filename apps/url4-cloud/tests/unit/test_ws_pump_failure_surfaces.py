"""A dead subscription must never masquerade as a healthy connection (OME-623).

INVARIANT: `Bridge._pump` runs as a background task. Nothing awaits it, so without a done-callback
its exception is swallowed entirely — while the writer keeps emitting heartbeats on idle. The
result is a permanently dead stream that is indistinguishable, from the client's side, from an
idle healthy one.

STORY: as a client I attach and then wait. The run completes, every frame lands in the stream, and
I receive nothing but heartbeats — no error, no close, and nothing in the server log either.
Observed on a live kind cluster; the only way to see the frames was to read JetStream out of band.

AIDEV-NOTE: `tests/unit/test_nats_bus_subscribe_ensures_stream.py` fixed the FIRST trigger of this
hazard (subscribe-before-stream-exists) by reordering `ensure_stream`. It did not close the
swallowed-exception hole itself, so a second trigger walked into the same dead end. These tests
pin the general behaviour — ANY pump failure surfaces — rather than one more trigger.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud_nats import InMemoryBus
from url4_streaming_protocol import OutboundFrame, StartedData, StartedEvent

SECRET = "ws-pump-secret"
WINDOW_S = 60
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)


class ExplodingBus(InMemoryBus):
    """A bus whose `subscribe` raises — standing in for ANY pump failure (a refused consumer
    config, a dropped broker, a purged stream).

    WHY subclass instead of hand-rolling the port: publish/ensure_stream/purge keep working, so
    the test isolates the one call the bridge runs as a bare background task.
    """

    async def subscribe(
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]:
        raise RuntimeError("consumer rejected: super-secret-broker-detail")
        yield  # pragma: no cover - unreachable; makes this an async generator


def _token(topic: str) -> str:
    return JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)


def _make_app(bus: Any) -> FastAPI:
    return create_app(
        Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S, nats_url="nats://unused:4222"),
        bus=bus,
        clock=lambda: T0,
    )


def _raw_attach(from_sequence: int | None) -> dict[str, Any]:
    # WHY hand-built rather than dumping an `AttachEvent`: `AttachData` now rejects
    # from_sequence < 1, so the typed model cannot express the malformed frame a real client can
    # still put on the wire — which is precisely the case under test.
    data = {} if from_sequence is None else {"from_sequence": from_sequence}
    return {
        "specversion": "1.0",
        "id": "att-raw",
        "source": "/client",
        "subject": "t",
        "type": "ai.url4.attach",
        "datacontenttype": "application/json",
        "data": data,
    }


def _started(topic: str) -> StartedEvent:
    return StartedEvent(
        id=f"s-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=StartedData(url4="gpt()"),
    )


def test_attach_below_one_is_nacked_instead_of_silently_killing_the_stream() -> None:
    """The original trigger: `from_sequence: 0` is now refused at the protocol edge, so the
    client is told immediately rather than left waiting on a stream that can never deliver."""
    topic = "ws-attach-zero"
    bus = InMemoryBus()
    app = _make_app(bus)
    with TestClient(app) as client:
        portal = client.portal
        assert portal is not None
        portal.call(bus.publish, topic, _started(topic))
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_raw_attach(0))
            frame = ws.receive_json()
    assert frame["type"] == "ai.url4.error"
    assert frame["data"]["code"] == "invalid_frame"


def test_any_pump_failure_reaches_the_client_as_an_error_frame() -> None:
    """The general fix: the client learns the subscription died, whatever killed it."""
    topic = "ws-pump-dies"
    app = _make_app(ExplodingBus())
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_raw_attach(None))
            frame = ws.receive_json()
    assert frame["type"] == "ai.url4.error"
    assert frame["data"]["code"] == "stream_failed"


def test_pump_failure_nack_does_not_leak_the_broker_message() -> None:
    """INVARIANT: the nack names the failure CLASS only. A broker error can carry connection
    strings or credentials, and this frame goes to the client; the detail belongs in the log."""
    topic = "ws-pump-leak"
    app = _make_app(ExplodingBus())
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_raw_attach(None))
            frame = ws.receive_json()
    assert "super-secret-broker-detail" not in frame["data"]["message"]
    assert "RuntimeError" in frame["data"]["message"]


def test_reattach_cancels_the_previous_pump_without_reporting_an_error() -> None:
    """Regression guard for the fix itself: re-attach cancels the prior pump, and `_teardown`
    cancels it on disconnect. Both are normal control flow — reporting them would spam a
    correctly-behaving client, so `CancelledError` must stay silent."""
    topic = "ws-reattach-silent"
    bus = InMemoryBus()
    app = _make_app(bus)
    with TestClient(app) as client:
        portal = client.portal
        assert portal is not None
        portal.call(bus.publish, topic, _started(topic))
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_raw_attach(None))
            assert ws.receive_json()["type"] == "ai.url4.started"
            ws.send_json(_raw_attach(1))  # cancels the first pump, starts a second
            frame = ws.receive_json()
    # The replay re-delivers seq 1; crucially it is NOT an error frame.
    assert frame["type"] == "ai.url4.started"
