from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from url4.streaming.protocol import OutboundFrame, StartedData, StartedEvent
from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.testing import InMemoryEventStream

SECRET = "ws-pump-secret"
WINDOW_S = 60
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)


class ExplodingBus(InMemoryEventStream):
    async def subscribe(
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]:
        raise RuntimeError("consumer rejected: super-secret-broker-detail")
        yield  # pragma: no cover - unreachable; makes this an async generator


def _token(topic: str) -> str:
    return JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)


def _make_app(stream: Any) -> FastAPI:
    return create_app(
        Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S, nats_url="nats://unused:4222"),
        stream=stream,
        clock=lambda: T0,
    )


def _raw_attach(from_sequence: int | None) -> dict[str, Any]:
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
    topic = "ws-attach-zero"
    stream = InMemoryEventStream()
    app = _make_app(stream)
    with TestClient(app) as client:
        portal = client.portal
        assert portal is not None
        portal.call(stream.publish, topic, _started(topic))
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_raw_attach(0))
            frame = ws.receive_json()
    assert frame["type"] == "ai.url4.error"
    assert frame["data"]["code"] == "invalid_frame"


def test_any_pump_failure_reaches_the_client_as_an_error_frame() -> None:
    topic = "ws-pump-dies"
    app = _make_app(ExplodingBus())
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_raw_attach(None))
            frame = ws.receive_json()
    assert frame["type"] == "ai.url4.error"
    assert frame["data"]["code"] == "stream_failed"


def test_pump_failure_nack_does_not_leak_the_broker_message() -> None:
    topic = "ws-pump-leak"
    app = _make_app(ExplodingBus())
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_raw_attach(None))
            frame = ws.receive_json()
    assert "super-secret-broker-detail" not in frame["data"]["message"]
    assert "RuntimeError" in frame["data"]["message"]


def test_reattach_cancels_the_previous_pump_without_reporting_an_error() -> None:
    topic = "ws-reattach-silent"
    stream = InMemoryEventStream()
    app = _make_app(stream)
    with TestClient(app) as client:
        portal = client.portal
        assert portal is not None
        portal.call(stream.publish, topic, _started(topic))
        with client.websocket_connect(f"/ws?ticket={_token(topic)}") as ws:
            ws.send_json(_raw_attach(None))
            assert ws.receive_json()["type"] == "ai.url4.started"
            ws.send_json(_raw_attach(1))
            frame = ws.receive_json()
    assert frame["type"] == "ai.url4.started"
