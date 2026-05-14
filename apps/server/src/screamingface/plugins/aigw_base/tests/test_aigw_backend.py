"""Unit tests for AigwBackend — mocks the gateway via httpx.MockTransport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from screamingface.plugins.aigw_base.backend import (
    AigwBackend,
    AigwGatewayError,
)
from screamingface.plugins.llm_base.errors import (
    AuthError,
    BackendError,
    CredentialNotFoundError,
)
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart


def _factory(transport: httpx.MockTransport):
    def factory(timeout: float):
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout))

    return factory


def _ok_response(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "model": "anthropic/claude-haiku-4-5",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        },
    )


@pytest.mark.anyio
async def test_happy_path_extracts_text() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.content.decode())
        return _ok_response("pong")

    backend = AigwBackend(
        gateway_url="http://127.0.0.1:9105",
        profile_name="default",
        gateway_provider="anthropic",
        http_client_factory=_factory(httpx.MockTransport(handler)),
    )
    result = await backend.run(
        [CoreMessage(role="user", content=[TextPart(text="hi")])],
        model="anthropic/claude-haiku-4-5",
        system="be terse",
        max_tokens=10,
    )
    assert isinstance(result, CoreMessage)
    assert isinstance(result.content, list)
    assert result.content[0].text == "pong"  # type: ignore[union-attr]

    assert captured["url"] == "http://127.0.0.1:9105/v1/chat/completions"
    assert captured["headers"]["x-profile"] == "default"
    assert captured["body"]["model"] == "anthropic/claude-haiku-4-5"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "be terse"}
    assert captured["body"]["messages"][1] == {"role": "user", "content": "hi"}
    assert captured["body"]["max_tokens"] == 10


@pytest.mark.anyio
async def test_string_content_passes_through() -> None:
    """CoreMessage.content can be a bare string; that should round-trip too."""

    def handler(_req: httpx.Request) -> httpx.Response:
        return _ok_response("ok")

    backend = AigwBackend(
        gateway_provider="anthropic", http_client_factory=_factory(httpx.MockTransport(handler))
    )
    await backend.run(
        [CoreMessage(role="user", content="bare string")],
        model="anthropic/claude-haiku-4-5",
    )


@pytest.mark.anyio
async def test_404_profile_not_found_maps_to_credential_not_found() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"detail": {"code": "profile_not_found", "provider": "anthropic", "name": "x"}},
        )

    backend = AigwBackend(
        profile_name="x",
        gateway_provider="anthropic",
        http_client_factory=_factory(httpx.MockTransport(handler)),
    )
    with pytest.raises(CredentialNotFoundError, match="not found"):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )


@pytest.mark.anyio
async def test_409_pending_auth_maps_to_auth_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": {"code": "profile_pending_auth"}})

    backend = AigwBackend(
        gateway_provider="anthropic", http_client_factory=_factory(httpx.MockTransport(handler))
    )
    with pytest.raises(AuthError, match="awaiting OAuth"):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )


@pytest.mark.anyio
async def test_401_auth_required_maps_to_auth_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"detail": {"code": "auth_required", "message": "refresh failed"}},
        )

    backend = AigwBackend(
        gateway_provider="anthropic", http_client_factory=_factory(httpx.MockTransport(handler))
    )
    with pytest.raises(AuthError, match="refresh failed"):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )


@pytest.mark.anyio
async def test_500_raises_aigw_gateway_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    backend = AigwBackend(
        gateway_provider="anthropic", http_client_factory=_factory(httpx.MockTransport(handler))
    )
    with pytest.raises(AigwGatewayError):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )


@pytest.mark.anyio
async def test_unreachable_raises_backend_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    backend = AigwBackend(
        gateway_provider="anthropic", http_client_factory=_factory(httpx.MockTransport(handler))
    )
    with pytest.raises(BackendError, match="unreachable"):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )
