from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest

from screamingface_engine.app import create_app
from screamingface_engine.catalog import GatewayModel, resolve_model_routes
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings

CONNECTION_ID = UUID("00000000-0000-0000-0000-000000000092")
GATEWAY_MODEL = "openrouter/anthropic/claude-opus-4.8"


def _connection() -> dict[str, object]:
    return {
        "id": str(CONNECTION_ID),
        "provider": "openrouter",
        "label": "default",
        "status": "active",
        "auth_type": "api_key",
        "account": None,
    }


@pytest.mark.asyncio
async def test_openrouter_api_key_connection_is_forwarded_and_sanitized() -> None:
    secret = "sk-or-private-connection-secret"
    calls: list[tuple[str, str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(200, json={"connections": []})
        assert body == {"provider": "openrouter", "label": "default", "api_key": secret}
        return httpx.Response(201, json=_connection())

    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(handler)
    )
    model_routes = resolve_model_routes((GatewayModel(GATEWAY_MODEL, "openrouter"),))
    app = create_app(
        model_routes=model_routes,
        settings=Settings(gateway_url="http://gateway.test"),
        gateway=gateway,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.put(
            "/v1/connections/openrouter/api-key",
            json={"api_key": secret},
        )
    await gateway.aclose()

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openrouter",
        "status": "connected",
        "auth_method": "api_key",
        "account_label": None,
    }
    assert calls == [
        ("GET", "/v1/oauth/connections", None),
        (
            "POST",
            "/v1/oauth/connections/api-key",
            {"provider": "openrouter", "label": "default", "api_key": secret},
        ),
    ]
    assert secret not in response.text


@pytest.mark.asyncio
async def test_openrouter_oauth_fails_before_gateway_traffic() -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("unsupported OAuth reached AI Gateway")
        ),
    )
    model_routes = resolve_model_routes((GatewayModel(GATEWAY_MODEL, "openrouter"),))
    app = create_app(
        model_routes=model_routes,
        settings=Settings(gateway_url="http://gateway.test"),
        gateway=gateway,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.post("/v1/connections/openrouter/oauth")
    await gateway.aclose()

    assert response.status_code == 400
    assert response.json()["code"] == "auth_method_not_supported"
