from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from url4_cloud.app import create_app
from url4_cloud.config import Settings
from url4_cloud.connections.port import (
    AuthMethod,
    Caller,
    Connection,
    ConnectionAlreadyConnected,
    ConnectionRejected,
    ConnectionStatus,
    OAuthAuthorization,
)
from url4_cloud.testing import InMemoryEventStream

pytestmark = pytest.mark.asyncio

SECRET = "sk-or-v1-route-secret"
EMAIL = "researcher@example.com"


class FakeConnections:
    def __init__(self) -> None:
        self.connection = self._connection()
        self.calls: list[tuple[str, Caller, str | None]] = []
        self.error: Exception | None = None

    async def list(self, caller: Caller) -> tuple[Connection, ...]:
        self.calls.append(("list", caller, None))
        self._raise()
        return (self.connection,)

    async def connect(self, caller: Caller, provider: str, api_key: str) -> Connection:
        self.calls.append(("connect", caller, api_key))
        self._raise()
        self.connection = self._connection(
            status="connected",
            auth_method="api_key",
        )
        return self.connection

    async def disconnect(self, caller: Caller, provider: str) -> Connection:
        self.calls.append(("disconnect", caller, provider))
        self._raise()
        self.connection = self._connection()
        return self.connection

    async def start_oauth(self, caller: Caller, provider: str) -> OAuthAuthorization:
        self.calls.append(("start_oauth", caller, provider))
        self._raise()
        return OAuthAuthorization(
            provider=provider,
            authorize_url="https://provider.example/authorize?state=private",
            expires_in=600,
        )

    async def aclose(self) -> None:
        return None

    @staticmethod
    def _connection(
        *,
        status: ConnectionStatus = "not_connected",
        auth_method: AuthMethod | None = None,
    ) -> Connection:
        return Connection(
            provider="openrouter",
            display_name="OpenRouter",
            auth_methods=("api_key",),
            status=status,
            auth_method=auth_method,
        )

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error


def _app(connections: FakeConnections | None) -> FastAPI:
    return create_app(
        Settings(jwt_secret="route-secret"),
        stream=InMemoryEventStream(),
        connections=connections,
    )


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_returns_one_automatic_openrouter_row() -> None:
    service = FakeConnections()

    async with _client(_app(service)) as client:
        response = await client.get("/v1/connections", headers={"X-User-Email": EMAIL})

    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [
            {
                "object": "connection",
                "provider": "openrouter",
                "display_name": "OpenRouter",
                "auth_methods": ["api_key"],
                "status": "not_connected",
                "auth_method": None,
                "account_label": None,
            }
        ],
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "X-User-Email"
    assert service.calls[0][1].identity == {"X-User-Email": EMAIL}


async def test_put_connects_without_returning_the_secret() -> None:
    service = FakeConnections()

    async with _client(_app(service)) as client:
        response = await client.put(
            "/v1/connections/openrouter",
            headers={"X-User-Email": EMAIL},
            json={"api_key": SECRET},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    assert SECRET not in response.text
    assert service.calls[-1][2] == SECRET


async def test_delete_returns_the_disconnected_row_and_is_idempotent() -> None:
    service = FakeConnections()

    async with _client(_app(service)) as client:
        first = await client.delete("/v1/connections/openrouter")
        second = await client.delete("/v1/connections/openrouter")

    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "not_connected"


async def test_post_oauth_returns_only_the_public_authorization_fields() -> None:
    service = FakeConnections()

    async with _client(_app(service)) as client:
        response = await client.post(
            "/v1/connections/anthropic/oauth",
            headers={"X-User-Email": EMAIL},
        )

    assert response.status_code == 201
    assert response.json() == {
        "object": "oauth_authorization",
        "provider": "anthropic",
        "authorize_url": "https://provider.example/authorize?state=private",
        "expires_in": 600,
    }
    assert service.calls[-1] == (
        "start_oauth",
        Caller({"X-User-Email": EMAIL}),
        "anthropic",
    )


async def test_invalid_keys_become_safe_rfc9457_problems() -> None:
    service = FakeConnections()
    service.error = ConnectionRejected("upstream body containing " + SECRET)

    async with _client(_app(service)) as client:
        response = await client.put(
            "/v1/connections/openrouter",
            json={"api_key": SECRET},
        )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert SECRET not in response.text


async def test_malformed_key_body_cannot_echo_the_secret() -> None:
    service = FakeConnections()

    async with _client(_app(service)) as client:
        response = await client.put(
            "/v1/connections/openrouter",
            json={"api_key": [SECRET]},
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Unprocessable Content",
        "status": 422,
        "detail": "the provider connection request is invalid",
    }
    assert SECRET not in response.text
    assert service.calls == []


async def test_existing_connection_conflict_is_a_safe_problem() -> None:
    service = FakeConnections()
    service.error = ConnectionAlreadyConnected()

    async with _client(_app(service)) as client:
        response = await client.post("/v1/connections/openrouter/oauth")

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == (
        "the provider is already connected; disconnect it before changing authentication"
    )


async def test_oauth_authorization_is_private_and_not_cacheable() -> None:
    async with _client(_app(FakeConnections())) as client:
        response = await client.post("/v1/connections/anthropic/oauth")

    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "X-User-Email"


async def test_unconfigured_connections_are_a_503() -> None:
    async with _client(_app(None)) as client:
        response = await client.get("/v1/connections")

    assert response.status_code == 503


async def test_connection_routes_are_published_in_openapi() -> None:
    schema = _app(FakeConnections()).openapi()
    paths = schema["paths"]

    assert "/v1/connections" in paths
    assert "/v1/connections/{provider}" in paths
    assert set(paths["/v1/connections/{provider}"]) >= {"put", "delete"}
    assert "post" in paths["/v1/connections/{provider}/oauth"]
    assert paths["/v1/connections"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/ConnectionListResponse"}
    assert paths["/v1/connections/{provider}"]["put"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ConnectionResponse"}
    assert paths["/v1/connections/{provider}"]["put"]["responses"]["422"]["content"][
        "application/problem+json"
    ]["schema"] == {"$ref": "#/components/schemas/Problem"}
