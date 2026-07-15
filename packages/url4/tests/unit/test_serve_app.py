"""Node wiring + the ASGI wrapper for `url4 serve` (url4._serve).

STORY: `url4 serve` exposes `GET /v1?q=<expr>` (the node eval path), dispatches
model routes to the aigateway, serves /healthz, and — beyond what Url4Node gives —
sheds load over max-inflight (503), bounds each request (504), and closes the
shared client on shutdown.

INVARIANT: the wrapper never double-sends — a timeout after the node has begun
responding is swallowed, not turned into a second (504) response.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from url4._serve import ServeConfig, build_asgi_app, build_client, build_node
from url4.server import Url4Node

pytestmark = pytest.mark.asyncio


def _gateway_client(recorder: list[httpx.Request]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        recorder.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "GW"}}]})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _driver(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://node")


async def test_eval_path_resolves_pure_expression() -> None:
    config = ServeConfig()
    async with _gateway_client([]) as client:
        app = build_asgi_app(build_node(config, client), client, config)
        async with _driver(app) as http:
            response = await http.get("/v1", params={"q": "('a', 'b')!'join'"})
    assert response.status_code == 200
    assert "join" in response.text


async def test_model_route_dispatches_to_aigateway() -> None:
    seen: list[httpx.Request] = []
    config = ServeConfig()
    client = _gateway_client(seen)
    app = build_asgi_app(build_node(config, client), client, config)
    async with _driver(app) as http:
        response = await http.get("/v1", params={"q": "(/claude(hi)!'go')"})
    await client.aclose()
    assert response.status_code == 200
    assert response.text == "GW"
    assert seen and "claude/claude-opus-4-8" in seen[0].content.decode()


async def test_healthz_needs_no_evaluation() -> None:
    config = ServeConfig()
    async with _gateway_client([]) as client:
        app = build_asgi_app(build_node(config, client), client, config)
        async with _driver(app) as http:
            response = await http.get("/healthz")
    assert response.status_code == 200
    assert response.text == "ok"


async def test_unknown_route_maps_to_404() -> None:
    config = ServeConfig()
    async with _gateway_client([]) as client:
        app = build_asgi_app(build_node(config, client), client, config)
        async with _driver(app) as http:
            response = await http.get("/v1", params={"q": "/nope(x)!go"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "endpoint_not_found"


async def test_parse_error_maps_to_400() -> None:
    config = ServeConfig()
    async with _gateway_client([]) as client:
        app = build_asgi_app(build_node(config, client), client, config)
        async with _driver(app) as http:
            response = await http.get("/v1", params={"q": "(a::)!'x'"})
    assert response.status_code == 400


async def test_over_max_inflight_returns_503() -> None:
    node = Url4Node("t", eval_path="/v1")
    gate = asyncio.Event()

    @node.endpoint("/slow")
    async def slow(request) -> str:  # noqa: ARG001 - handler contract
        await gate.wait()
        return "done"

    config = ServeConfig(routes={"/slow": "m"}, processor="/slow", max_inflight=1, timeout=5.0)
    async with httpx.AsyncClient() as unused:  # no LLM route is hit; client is just plumbing
        app = build_asgi_app(node, unused, config)
        async with _driver(app) as http:
            first = asyncio.create_task(http.get("/v1", params={"q": "(/slow(x)!'go')"}))
            await asyncio.sleep(0.1)  # let the first request enter and hold the only slot
            second = await http.get("/v1", params={"q": "(/slow(x)!'go')"})
            assert second.status_code == 503
            assert second.headers["retry-after"] == "1"
            gate.set()
            assert (await first).status_code == 200


async def test_request_timeout_returns_504() -> None:
    node = Url4Node("t", eval_path="/v1")

    @node.endpoint("/slow")
    async def slow(request) -> str:  # noqa: ARG001 - handler contract
        await asyncio.sleep(5)
        return "done"

    config = ServeConfig(routes={"/slow": "m"}, processor="/slow", timeout=0.05)
    async with httpx.AsyncClient() as unused:  # no LLM route is hit; client is just plumbing
        app = build_asgi_app(node, unused, config)
        async with _driver(app) as http:
            response = await http.get("/v1", params={"q": "(/slow(x)!'go')"})
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "timeout"


async def test_command_route_wires_through_node() -> None:
    config = ServeConfig(
        routes={"/claude": "m"},
        commands={"/echo": ("python3", "-c", "import sys; sys.stdout.write(sys.stdin.read())")},
        processor="/claude",
    )
    async with httpx.AsyncClient() as client:
        node = build_node(config, client)
        result = await node.evaluate("(/echo(ping)!'noop')")
    assert "ping" in result.text


async def test_build_client_is_an_async_client() -> None:
    client = build_client(ServeConfig(timeout=5.0))
    assert isinstance(client, httpx.AsyncClient)
    await client.aclose()


async def test_lifespan_closes_client_and_node() -> None:
    node = Url4Node("t")
    client = httpx.AsyncClient()
    app = build_asgi_app(node, client, ServeConfig())
    sent: list[str] = []
    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])

    async def receive() -> dict:
        return next(messages)

    async def send(message: dict) -> None:
        sent.append(message["type"])

    await app({"type": "lifespan"}, receive, send)
    assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"]
    assert client.is_closed
