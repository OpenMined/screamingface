from __future__ import annotations

import asyncio
import json
from collections.abc import MutableMapping
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from url4 import Url4Node

from screamingface_engine.asgi import EngineASGI
from screamingface_engine.gateway import GatewayClient


def _gateway() -> GatewayClient:
    return GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        ),
    )


@pytest.mark.asyncio
async def test_engine_asgi_rejects_above_global_inflight_limit() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    node = Url4Node("test")
    node.data("/healthz", "ok")

    @node.endpoint("/slow")
    async def slow(_request) -> str:
        entered.set()
        await release.wait()
        return "done"

    gateway = _gateway()
    app = EngineASGI(node, gateway, max_inflight=1, timeout=5)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        first = asyncio.create_task(client.get("/slow", params={"q": "()!wait"}))
        await entered.wait()
        rejected = await client.get("/healthz")
        release.set()
        completed = await first
    await gateway.aclose()

    assert completed.text == "done"
    assert rejected.status_code == 503
    assert rejected.json()["error"]["code"] == "overloaded"
    assert rejected.headers["retry-after"] == "1"


@pytest.mark.asyncio
async def test_engine_asgi_times_out_whole_evaluation() -> None:
    node = Url4Node("test")

    @node.endpoint("/slow")
    async def slow(_request) -> str:
        await asyncio.sleep(1)
        return "late"

    gateway = _gateway()
    app = EngineASGI(node, gateway, max_inflight=1, timeout=0.01)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get("/slow", params={"q": "()!wait"})
    await gateway.aclose()

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "timeout"


@pytest.mark.asyncio
async def test_engine_asgi_streams_lifecycle_and_unchanged_url4_value() -> None:
    node = Url4Node("test", eval_path="/v1")
    node.data("/value", "done")
    gateway = _gateway()
    app = EngineASGI(node, gateway, max_inflight=1, timeout=1)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        streamed = await client.get(
            "/v1",
            params={"q": "/value"},
            headers={"accept": "text/event-stream"},
        )
        plain = await client.get("/v1", params={"q": "/value"})
    await gateway.aclose()

    events = _events(streamed.text)
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert streamed.headers["cache-control"] == "no-cache"
    assert [event[0] for event in events] == ["accepted", "complete"]
    assert events[-1][1] == {
        "schema": "screamingface.evaluation-event.v1",
        "type": "complete",
        "content_type": "text/plain",
        "value": "done",
    }
    assert plain.status_code == 200
    assert plain.headers["content-type"].startswith("text/plain")
    assert plain.text == "done"


@pytest.mark.asyncio
async def test_engine_asgi_streams_running_and_typed_error_events() -> None:
    node = Url4Node("test", eval_path="/v1")

    @node.endpoint("/slow")
    async def slow(_request) -> str:
        await asyncio.sleep(0.03)
        return "done"

    gateway = _gateway()
    app = EngineASGI(
        node,
        gateway,
        max_inflight=1,
        timeout=1,
        stream_interval=0.005,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        running = await client.get(
            "/v1",
            params={"q": "/slow()!'wait'"},
            headers={"accept": "text/event-stream"},
        )
        failed = await client.get(
            "/v1",
            params={"q": "("},
            headers={"accept": "text/event-stream"},
        )
    await gateway.aclose()

    running_events = _events(running.text)
    assert running_events[0][0] == "accepted"
    assert any(name == "running" for name, _payload in running_events)
    assert running_events[-1][0] == "complete"
    failed_events = _events(failed.text)
    assert [name for name, _payload in failed_events] == ["accepted", "error"]
    assert failed_events[-1][1]["status"] == 400
    assert failed_events[-1][1]["error"]["code"] == "malformed_source"


@pytest.mark.asyncio
async def test_engine_asgi_stream_timeout_is_a_terminal_event() -> None:
    node = Url4Node("test", eval_path="/v1")

    @node.endpoint("/slow")
    async def slow(_request) -> str:
        await asyncio.sleep(1)
        return "late"

    gateway = _gateway()
    app = EngineASGI(
        node,
        gateway,
        max_inflight=1,
        timeout=0.02,
        stream_interval=0.005,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get(
            "/v1",
            params={"q": "/slow()!'wait'"},
            headers={"accept": "text/event-stream"},
        )
    await gateway.aclose()

    events = _events(response.text)
    assert events[0][0] == "accepted"
    assert events[-1] == (
        "error",
        {
            "schema": "screamingface.evaluation-event.v1",
            "type": "error",
            "status": 504,
            "error": {"code": "timeout", "message": "evaluation exceeded 0.02s"},
        },
    )


@pytest.mark.asyncio
async def test_engine_asgi_owns_gateway_and_node_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node = Url4Node("test")
    gateway = _gateway()
    start = AsyncMock()
    close_gateway = AsyncMock()
    close_node = AsyncMock()
    monkeypatch.setattr(gateway, "start", start)
    monkeypatch.setattr(gateway, "aclose", close_gateway)
    monkeypatch.setattr(node, "aclose", close_node)
    app = EngineASGI(node, gateway, max_inflight=1, timeout=1)
    received = iter(
        [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
    )
    sent: list[MutableMapping[str, Any]] = []

    async def receive() -> MutableMapping[str, Any]:
        return next(received)

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)

    await app({"type": "lifespan"}, receive, send)

    start.assert_awaited_once()
    close_gateway.assert_awaited_once()
    close_node.assert_awaited_once()
    assert sent == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]


def _events(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        assert lines[0].startswith("event: ")
        assert lines[1].startswith("data: ")
        events.append((lines[0][7:], json.loads(lines[1][6:])))
    return events
