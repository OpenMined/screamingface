from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from model_fixtures import MODEL_ROUTES

from screamingface_engine.app import create_app
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings

CODEX_ID = UUID("00000000-0000-0000-0000-000000000001")
GEMINI_ID = UUID("00000000-0000-0000-0000-000000000002")


def _gateway_connection(
    provider: str,
    connection_id: UUID,
    *,
    status: str = "active",
    auth_type: str = "oauth",
    account: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": str(connection_id),
        "account_id": "10000000-0000-0000-0000-000000000000",
        "provider": provider,
        "label": "default",
        "status": status,
        "auth_type": auth_type,
        "account": account,
        "credential_locator": {"service": "private", "account": "private"},
        "created_at": datetime.now(UTC).isoformat(),
        "last_used_at": None,
        "last_refreshed_at": None,
        "error_message": None,
        "is_duplicate": False,
    }


def _settings() -> Settings:
    return Settings(gateway_url="http://gateway.test")


@pytest.mark.asyncio
async def test_registry_advertises_public_provider_ownership_without_gateway_aliases() -> None:
    app = create_app(model_routes=MODEL_ROUTES, settings=_settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get("/.well-known/screamingface")

    registry = response.json()
    assert registry["providers"] == [
        {"id": "codex", "display_name": "OpenAI Codex", "auth_methods": ["oauth"]},
        {
            "id": "gemini",
            "display_name": "Google Gemini",
            "auth_methods": ["api_key"],
        },
        {
            "id": "anthropic",
            "display_name": "Anthropic",
            "auth_methods": ["oauth", "api_key"],
        },
        {
            "id": "openrouter",
            "display_name": "OpenRouter",
            "auth_methods": ["api_key"],
        },
        {
            "id": "huggingface",
            "display_name": "Hugging Face",
            "auth_methods": ["api_key"],
        },
        {
            "id": "tavily",
            "display_name": "Tavily",
            "auth_methods": ["api_key"],
        },
    ]
    assert [model["provider"] for model in registry["models"]] == [
        "codex",
        "gemini",
        "anthropic",
    ]
    assert "gemini-cli" not in response.text
    assert "credential_locator" not in response.text


@pytest.mark.asyncio
async def test_gemini_oauth_is_not_startable_while_api_keys_remain_advertised() -> None:
    app = create_app(model_routes=MODEL_ROUTES, settings=_settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.post("/v1/connections/gemini/oauth")

    assert response.status_code == 400
    assert response.json()["code"] == "auth_method_not_supported"


@pytest.mark.asyncio
async def test_connection_list_and_status_are_sanitized_and_fresh() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        assert request.url.path == "/v1/oauth/connections"
        calls += 1
        return httpx.Response(
            200,
            json={
                "connections": [
                    _gateway_connection(
                        "codex",
                        CODEX_ID,
                        account={
                            "sub": "private-subject",
                            "email": "researcher@example.com",
                            "name": "Researcher",
                            "raw": {"private": "claim"},
                        },
                    )
                ]
            },
        )

    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(handler)
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=_settings(), gateway=gateway)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        listed = await client.get("/v1/connections")
        status = await client.get("/v1/connections/codex")
    await gateway.aclose()

    assert listed.json() == {
        "schema": "screamingface.connections.v1",
        "connections": [
            {
                "provider": "codex",
                "status": "connected",
                "auth_method": "oauth",
                "account_label": "researcher@example.com",
            },
            {
                "provider": "gemini",
                "status": "not_connected",
                "auth_method": None,
                "account_label": None,
            },
            {
                "provider": "anthropic",
                "status": "not_connected",
                "auth_method": None,
                "account_label": None,
            },
            {
                "provider": "openrouter",
                "status": "not_connected",
                "auth_method": None,
                "account_label": None,
            },
            {
                "provider": "huggingface",
                "status": "not_connected",
                "auth_method": None,
                "account_label": None,
            },
            {
                "provider": "tavily",
                "status": "not_connected",
                "auth_method": None,
                "account_label": None,
            },
        ],
    }
    assert status.json() == listed.json()["connections"][0]
    assert calls == 2
    assert "private-subject" not in listed.text
    assert "credential_locator" not in listed.text


@pytest.mark.asyncio
async def test_api_key_put_creates_gateway_connection_without_echoing_secret() -> None:
    secret = "sentinel-super-secret-api-key"
    seen: list[tuple[str, str, bytes]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), await request.aread()))
        if request.method == "GET":
            return httpx.Response(200, json={"connections": []})
        assert request.url.path == "/v1/oauth/connections/api-key"
        assert json.loads(request.content) == {
            "provider": "gemini-cli",
            "label": "default",
            "api_key": secret,
        }
        return httpx.Response(
            201,
            json=_gateway_connection("gemini-cli", GEMINI_ID, auth_type="api_key"),
        )

    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(handler)
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=_settings(), gateway=gateway)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.put(
            "/v1/connections/gemini/api-key",
            json={"api_key": secret},
        )
    await gateway.aclose()

    assert response.status_code == 200
    assert response.json() == {
        "provider": "gemini",
        "status": "connected",
        "auth_method": "api_key",
        "account_label": None,
    }
    assert secret not in str(seen[0][1])
    assert secret not in response.text


@pytest.mark.asyncio
async def test_oauth_start_and_provider_callback_remain_engine_owned() -> None:
    seen: list[tuple[str, str, dict[str, object] | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/v1/oauth/connections":
            return httpx.Response(200, json={"connections": []})
        if request.url.path == "/v1/oauth/connections" and request.method == "POST":
            assert body == {
                "provider": "codex",
                "label": "default",
                "redirect_uri": "http://localhost:1455/auth/callback",
            }
            return httpx.Response(
                201,
                json={
                    "connection_id": str(CODEX_ID),
                    "authorize_url": (
                        "https://auth.openai.example/authorize?"
                        "redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback"
                    ),
                    "state": "gateway-state",
                    "expires_in": 600,
                },
            )
        assert request.url.path == "/v1/auth/codex/exchange-code"
        assert dict(request.url.params) == {}
        assert body == {"code": "provider-code", "state": "gateway-state"}
        return httpx.Response(200, json={"state": "authenticated"})

    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(handler)
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=_settings(), gateway=gateway)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        started = await client.post("/v1/connections/codex/oauth")
        callback = await client.get(
            "/auth/callback",
            params={"code": "provider-code", "state": "gateway-state", "scope": "ignored"},
        )
    await gateway.aclose()

    assert started.json() == {
        "provider": "codex",
        "status": "pending",
        "authorize_url": (
            "https://auth.openai.example/authorize?"
            "redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback"
        ),
        "expires_in": 600,
    }
    assert callback.status_code == 200
    assert callback.headers["content-type"].startswith("text/html")
    assert "Authentication complete" in callback.text
    assert "gateway private callback response" not in callback.text
    assert seen[-1] == (
        "POST",
        "/v1/auth/codex/exchange-code",
        {"code": "provider-code", "state": "gateway-state"},
    )


@pytest.mark.asyncio
async def test_disconnect_is_idempotent_and_does_not_invent_gateway_ids() -> None:
    calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"connections": []})
        pytest.fail("disconnect sent an unnecessary Gateway mutation")

    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(handler)
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=_settings(), gateway=gateway)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        first = await client.delete("/v1/connections/gemini")
        second = await client.delete("/v1/connections/gemini")
    await gateway.aclose()

    assert first.status_code == second.status_code == 204
    assert calls == [
        ("GET", "/v1/oauth/connections"),
        ("GET", "/v1/oauth/connections"),
    ]


@pytest.mark.asyncio
async def test_connection_routes_reject_unknown_providers_and_malformed_secret_bodies() -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("invalid request reached AI Gateway")
        ),
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=_settings(), gateway=gateway)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        unknown = await client.get("/v1/connections/private-alias")
        wrong_type = await client.put(
            "/v1/connections/gemini/api-key",
            content='{"api_key": 42}',
            headers={"content-type": "application/json"},
        )
        duplicate = await client.put(
            "/v1/connections/gemini/api-key",
            content='{"api_key":"first","api_key":"sentinel-second"}',
            headers={"content-type": "application/json"},
        )
    await gateway.aclose()

    assert unknown.status_code == 404
    assert unknown.json()["code"] == "unknown_provider"
    assert wrong_type.status_code == duplicate.status_code == 400
    assert wrong_type.json()["code"] == duplicate.json()["code"] == "invalid_api_key"
    assert "sentinel-second" not in duplicate.text


@pytest.mark.asyncio
async def test_gateway_connection_failure_is_normalized_without_unsafe_body() -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(503, text="private upstream diagnostic")
        ),
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=_settings(), gateway=gateway)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get("/v1/connections")
    await gateway.aclose()

    assert response.status_code == 503
    assert response.json() == {
        "schema": "screamingface.error.v1",
        "code": "gateway_unavailable",
        "message": "AI Gateway is temporarily unavailable.",
        "provider": None,
        "retryable": True,
    }
    assert "private upstream diagnostic" not in response.text


@pytest.mark.asyncio
async def test_model_dispatch_selects_the_engine_managed_default_connection() -> None:
    profile_headers: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        profile_headers.append(request.headers.get("x-profile"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "A"}}]})

    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(handler)
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=_settings(), gateway=gateway)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get("/codex/gpt-5.5", params={"q": "Question"})
    await gateway.aclose()

    assert response.status_code == 200
    assert profile_headers == ["default"]
