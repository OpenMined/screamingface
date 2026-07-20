from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from screamingface_engine.app import create_app
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings, SettingsError
from screamingface_engine.web_research import WebResearchClient


async def _public_address(_host: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


def test_phase4d_settings_resolve_and_validate_web_configuration() -> None:
    settings = Settings.from_env(
        {
            "SCREAMINGFACE_SEARXNG_URL": "http://searxng:8080/",
            "SCREAMINGFACE_WEB_TIMEOUT": "12.5",
            "SCREAMINGFACE_WEB_MAX_RESULTS": "4",
            "SCREAMINGFACE_WEB_MAX_TOOL_CALLS": "9",
            "SCREAMINGFACE_WEB_MAX_CONTENT_CHARS": "12000",
            "SCREAMINGFACE_WEB_MAX_FETCH_BYTES": "100000",
        }
    )

    assert settings.searxng_url == "http://searxng:8080"
    assert settings.web_timeout == 12.5
    assert settings.web_max_results == 4
    assert settings.web_max_tool_calls == 9
    assert settings.web_max_content_chars == 12_000
    assert settings.web_max_fetch_bytes == 100_000

    invalid = (
        ({"SCREAMINGFACE_SEARXNG_URL": "searxng:8080"}, "absolute http"),
        ({"SCREAMINGFACE_WEB_TIMEOUT": "0"}, "positive finite"),
        ({"SCREAMINGFACE_WEB_MAX_RESULTS": "0"}, "at least 1"),
        ({"SCREAMINGFACE_WEB_MAX_TOOL_CALLS": "0"}, "at least 1"),
        ({"SCREAMINGFACE_WEB_MAX_CONTENT_CHARS": "0"}, "at least 1"),
        ({"SCREAMINGFACE_WEB_MAX_FETCH_BYTES": "0"}, "at least 1"),
    )
    for env, message in invalid:
        with pytest.raises(SettingsError, match=message):
            Settings.from_env(env)


@pytest.mark.asyncio
async def test_configured_app_advertises_and_executes_web_search_as_plaintext() -> None:
    gateway_requests: list[dict[str, object]] = []

    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        gateway_requests.append(body)
        if len(gateway_requests) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "search_1",
                                        "type": "function",
                                        "function": {
                                            "name": "web_search",
                                            "arguments": '{"query":"Jetson Orin"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Researched answer"}}]},
        )

    async def search_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Source",
                        "url": "https://example.org/source",
                        "content": "Evidence",
                    }
                ]
            },
        )

    settings = Settings(searxng_url="http://search.test")
    assert settings.searxng_url is not None
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(gateway_handler),
    )
    research = WebResearchClient(
        settings.searxng_url,
        timeout=settings.web_timeout,
        max_results=settings.web_max_results,
        max_content_chars=settings.web_max_content_chars,
        max_fetch_bytes=settings.web_max_fetch_bytes,
        transport=httpx.MockTransport(search_handler),
        resolver=_public_address,
    )
    app = create_app(settings=settings, gateway=gateway, research=research)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        registry = json.loads((await client.get("/.well-known/screamingface")).text)
        response = await client.get(
            "/claude/sonnet-4.6",
            params={
                "tools": "web_search",
                "q": "(Compare Jetson models)!Answer with sources",
            },
        )
    await gateway.aclose()
    await research.aclose()

    assert registry["models"] == [
        {"id": "codex/gpt-5.5", "provider": "codex", "supported_tools": []},
        {"id": "gemini/3.5-flash", "provider": "gemini", "supported_tools": []},
        {
            "id": "claude/sonnet-4.6",
            "provider": "anthropic",
            "supported_tools": ["web_search"],
        },
        {
            "id": "gemini/3.1-pro-preview",
            "provider": "gemini",
            "supported_tools": [],
        },
    ]
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "Researched answer"
    assert len(gateway_requests) == 2
    assert gateway_requests[0]["tools"]
    messages = gateway_requests[1]["messages"]
    assert isinstance(messages, list)
    assert isinstance(messages[-1], dict)
    assert messages[-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_engine_lifespan_owns_research_client() -> None:
    settings = Settings(searxng_url="http://search.test")
    assert settings.searxng_url is not None
    gateway = GatewayClient("http://gateway.test", timeout=5)
    research = WebResearchClient(
        settings.searxng_url,
        timeout=settings.web_timeout,
        max_results=settings.web_max_results,
        max_content_chars=settings.web_max_content_chars,
        max_fetch_bytes=settings.web_max_fetch_bytes,
        resolver=_public_address,
    )
    start_gateway = AsyncMock()
    close_gateway = AsyncMock()
    start_research = AsyncMock()
    close_research = AsyncMock()
    gateway.start = start_gateway
    gateway.aclose = close_gateway
    research.start = start_research
    research.aclose = close_research
    app = create_app(settings=settings, gateway=gateway, research=research)
    received = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent: list[MutableMapping[str, Any]] = []

    async def receive() -> MutableMapping[str, Any]:
        return next(received)

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)

    await app({"type": "lifespan"}, receive, send)

    start_gateway.assert_awaited_once()
    start_research.assert_awaited_once()
    close_gateway.assert_awaited_once()
    close_research.assert_awaited_once()
    assert sent == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]


@pytest.mark.asyncio
async def test_engine_lifespan_cleans_up_when_research_startup_fails() -> None:
    settings = Settings(searxng_url="http://search.test")
    assert settings.searxng_url is not None
    gateway = GatewayClient("http://gateway.test", timeout=5)
    research = WebResearchClient(
        settings.searxng_url,
        timeout=settings.web_timeout,
        max_results=settings.web_max_results,
        max_content_chars=settings.web_max_content_chars,
        max_fetch_bytes=settings.web_max_fetch_bytes,
        resolver=_public_address,
    )
    gateway.start = AsyncMock()
    gateway.aclose = AsyncMock()
    research.start = AsyncMock(side_effect=RuntimeError("search unavailable"))
    research.aclose = AsyncMock()
    app = create_app(settings=settings, gateway=gateway, research=research)
    received = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent: list[MutableMapping[str, Any]] = []

    async def receive() -> MutableMapping[str, Any]:
        return next(received)

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)

    await app({"type": "lifespan"}, receive, send)

    assert sent == [
        {"type": "lifespan.startup.failed", "message": "search unavailable"},
        {"type": "lifespan.shutdown.complete"},
    ]
    assert gateway.aclose.await_count == 2
    assert research.aclose.await_count == 2


@pytest.mark.asyncio
async def test_engine_preserves_safe_gateway_code_without_private_detail() -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                503,
                json={
                    "detail": {
                        "code": "provider_unavailable",
                        "message": "private bearer-secret-123",
                    }
                },
            )
        ),
    )
    app = create_app(settings=Settings(), gateway=gateway)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get(
            "/gemini/3.5-flash",
            params={"q": "(Question)!Answer"},
        )
    await gateway.aclose()

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "provider_unavailable",
            "message": "AI Gateway returned HTTP 503 (provider_unavailable) for 'gemini/3.5-flash'",
        }
    }
    assert "bearer-secret-123" not in response.text
