from __future__ import annotations

import json

import httpx
import pytest

from screamingface.gateway import AIGatewayClient


class GatewayRecorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._response(request)

    def _response(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            response = httpx.Response(200, json={"status": "ok"})
        elif request.url.path == "/v1/auth/login":
            assert json.loads(request.content) == {
                "username": "admin",
                "password": "password123",
            }
            response = httpx.Response(200, json=_login_payload())
        elif request.url.path == "/v1/models":
            assert request.headers["Authorization"] == "Bearer gateway-jwt"
            response = httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": "codex/gpt-5.5", "owned_by": "codex"},
                        {"id": "claude-sonnet-4-6", "owned_by": "anthropic"},
                    ],
                },
            )
        elif request.url.path == "/v1/oauth/connections":
            response = httpx.Response(200, json={"connections": []})
        elif request.url.path == "/v1/chat/completions":
            assert request.headers["Authorization"] == "Bearer gateway-jwt"
            assert request.headers["X-Profile"] == "work"
            response = httpx.Response(200, json=_completion_payload())
        else:
            response = httpx.Response(404)
        return response


def _login_payload() -> dict:
    return {
        "token": "gateway-jwt",
        "expires_at": "2030-01-01T00:00:00Z",
        "account": {
            "id": "00000000-0000-0000-0000-000000000001",
            "username": "admin",
            "display_name": None,
            "created_at": "2026-01-01T00:00:00Z",
            "last_login_at": None,
            "is_active": True,
        },
    }


def _completion_payload() -> dict:
    return {
        "choices": [{"message": {"content": "B"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
    }


@pytest.mark.asyncio
async def test_gateway_client_login_models_connections_and_chat() -> None:
    recorder = GatewayRecorder()
    client = AIGatewayClient(
        "https://gateway.example",
        transport=httpx.MockTransport(recorder),
    )

    assert await client.health() is True
    session = await client.login("admin", "password123")
    assert session.token == "gateway-jwt"
    assert await client.list_models() == [
        "codex/gpt-5.5",
        "anthropic/claude-sonnet-4-6",
    ]
    assert await client.list_connections() == []
    completion = await client.complete(
        model="codex/gpt-5.5",
        messages=[{"role": "user", "content": "Pick A-D"}],
        profile="work",
    )
    assert completion.text == "B"
    assert completion.total_tokens == 11

    await client.aclose()
    assert len(recorder.requests) == 5


def test_gateway_client_repr_never_contains_token() -> None:
    client = AIGatewayClient("https://gateway.example", token="gateway-jwt-secret")

    assert "gateway-jwt-secret" not in repr(client)
