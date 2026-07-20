from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest
from model_fixtures import MODEL_ROUTES

from screamingface_engine.app import create_app
from screamingface_engine.asgi import EngineASGI
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings

CONNECTION_ID = UUID("00000000-0000-0000-0000-000000000010")


def _record(
    *,
    provider: str = "gemini-cli",
    label: str = "default",
    status: str = "active",
    auth_type: str = "api_key",
    account: object = None,
) -> dict[str, object]:
    return {
        "id": str(CONNECTION_ID),
        "provider": provider,
        "label": label,
        "status": status,
        "auth_type": auth_type,
        "account": account,
    }


def _app(handler) -> tuple[EngineASGI, GatewayClient]:
    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(handler)
    )
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=Settings(gateway_url="http://gateway.test"),
        gateway=gateway,
    )
    return app, gateway


@pytest.mark.asyncio
async def test_api_key_replacement_uses_the_existing_connection_id() -> None:
    secret = "replacement-secret"
    calls: list[tuple[str, str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(200, json={"connections": [_record()]})
        assert request.method == "PUT"
        return httpx.Response(200, json=_record())

    app, gateway = _app(handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.put("/v1/connections/gemini/api-key", json={"api_key": secret})
    await gateway.aclose()

    assert response.status_code == 200
    assert calls == [
        ("GET", "/v1/oauth/connections", None),
        ("PUT", f"/v1/oauth/connections/{CONNECTION_ID}/api-key", {"api_key": secret}),
    ]


@pytest.mark.asyncio
async def test_changing_auth_method_revokes_the_old_connection_before_create() -> None:
    calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"connections": [_record(provider="gemini-cli", auth_type="oauth")]},
            )
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(201, json=_record())

    app, gateway = _app(handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.put(
            "/v1/connections/gemini/api-key", json={"api_key": "new-api-key"}
        )
    await gateway.aclose()

    assert response.status_code == 200
    assert calls == [
        ("GET", "/v1/oauth/connections"),
        ("DELETE", f"/v1/oauth/connections/{CONNECTION_ID}"),
        ("POST", "/v1/oauth/connections/api-key"),
    ]


@pytest.mark.asyncio
async def test_oauth_reconnect_and_disconnect_revoke_existing_connections() -> None:
    calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"connections": [_record(provider="codex", auth_type="oauth")]},
            )
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(
            201,
            json={
                "connection_id": str(CONNECTION_ID),
                "authorize_url": "https://auth.example/authorize",
                "state": "state",
                "expires_in": 600,
            },
        )

    app, gateway = _app(handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        started = await client.post("/v1/connections/codex/oauth")
        disconnected = await client.delete("/v1/connections/codex")
    await gateway.aclose()

    assert started.status_code == 200
    assert disconnected.status_code == 204
    assert calls.count(("DELETE", f"/v1/oauth/connections/{CONNECTION_ID}")) == 2


@pytest.mark.asyncio
async def test_status_projection_handles_reauth_and_ignores_unmanaged_labels() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "connections": [
                    _record(
                        provider="codex",
                        status="pending",
                        auth_type="oauth",
                        account={"name": "Pending Researcher"},
                    ),
                    _record(provider="gemini-cli", status="expired", auth_type="api_key"),
                    _record(
                        provider="anthropic",
                        status="error",
                        auth_type="oauth",
                        account={"sub": "anthropic-subject"},
                    ),
                    _record(provider="gemini-cli", label="unrelated"),
                    _record(provider="huggingface", label="other"),
                ]
            },
        )

    app, gateway = _app(handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get("/v1/connections")
    await gateway.aclose()

    connections = response.json()["connections"]
    assert [item["status"] for item in connections] == [
        "pending",
        "needs_reauth",
        "needs_reauth",
    ]
    assert connections[0]["account_label"] == "Pending Researcher"
    assert connections[2]["account_label"] == "anthropic-subject"


@pytest.mark.asyncio
async def test_control_plane_enforces_methods_content_types_and_body_limits() -> None:
    app, gateway = _app(lambda _request: pytest.fail("invalid input reached Gateway"))
    oversized = "x" * 16_385
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        method = await client.post("/v1/connections")
        content_type = await client.put("/v1/connections/gemini/api-key", content="api-key")
        too_large = await client.put(
            "/v1/connections/gemini/api-key",
            json={"api_key": oversized},
        )
        body = await client.post(
            "/v1/connections/codex/oauth",
            json={"unexpected": True},
        )
        route = await client.get("/v1/connections/codex/unknown")
    await gateway.aclose()

    assert method.status_code == 405
    assert content_type.status_code == 415
    assert too_large.status_code == 413
    assert body.status_code == 400
    assert route.status_code == 404


@pytest.mark.asyncio
async def test_callback_failures_are_generic_and_preserve_gateway_status() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="private callback diagnostic")

    app, gateway = _app(handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        wrong_method = await client.post("/auth/callback")
        missing = await client.get("/oauth2callback", params={"code": "only-code"})
        unavailable = await client.get("/callback", params={"code": "code", "state": "state"})
    await gateway.aclose()

    assert wrong_method.status_code == 405
    assert missing.status_code == 400
    assert unavailable.status_code == 503
    assert "private callback diagnostic" not in unavailable.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("gateway_failure", "status", "code"),
    [
        (httpx.ConnectError("private offline detail"), 503, "gateway_unavailable"),
        (httpx.ReadTimeout("private timeout detail"), 504, "gateway_timeout"),
    ],
)
async def test_gateway_transport_failures_are_safe(
    gateway_failure: httpx.RequestError, status: int, code: str
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise gateway_failure

    app, gateway = _app(handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get("/v1/connections")
    await gateway.aclose()

    assert response.status_code == status
    assert response.json()["code"] == code
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_gateway_connection_responses_are_byte_bounded() -> None:
    app, gateway = _app(lambda _request: httpx.Response(200, content=b"x" * 262_145))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get("/v1/connections")
    await gateway.aclose()

    assert response.status_code == 502
    assert response.json()["code"] == "gateway_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("gateway_response", "expected_code"),
    [
        (httpx.Response(400, json={"detail": {"code": "invalid_api_key"}}), "invalid_api_key"),
        (
            httpx.Response(400, json={"detail": {"code": "api_key_not_supported"}}),
            "auth_method_not_supported",
        ),
        (
            httpx.Response(401, json={"detail": {"code": "auth_required"}}),
            "connection_needs_reauth",
        ),
        (httpx.Response(403, json={"detail": {"code": "denied"}}), "provider_access_denied"),
    ],
)
async def test_gateway_error_codes_are_normalized(
    gateway_response: httpx.Response, expected_code: str
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"connections": []})
        return gateway_response

    app, gateway = _app(handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.put("/v1/connections/gemini/api-key", json={"api_key": "valid-key"})
    await gateway.aclose()

    assert response.json()["code"] == expected_code


@pytest.mark.asyncio
async def test_unsupported_auth_method_is_rejected_before_gateway() -> None:
    app, gateway = _app(lambda _request: pytest.fail("unsupported method reached Gateway"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.put("/v1/connections/codex/api-key", json={"api_key": "valid-key"})
    await gateway.aclose()

    assert response.status_code == 400
    assert response.json()["code"] == "auth_method_not_supported"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"connections": {}},
        {"connections": [42]},
        {"connections": [_record(status="unexpected")]},
        {"connections": [{**_record(), "id": "not-a-uuid"}]},
        {"connections": [{**_record(), "account": 42}]},
        {"connections": [_record(), _record()]},
        {"connections": [], "unknown": True},
        [],
    ],
)
async def test_malformed_gateway_connection_documents_fail_closed(payload: object) -> None:
    app, gateway = _app(lambda _request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get("/v1/connections")
    await gateway.aclose()

    assert response.status_code == 502
    assert response.json()["code"] == "gateway_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "oauth_response",
    [
        {
            "connection_id": str(CONNECTION_ID),
            "authorize_url": "http://unsafe.example/authorize",
            "state": "state",
            "expires_in": 600,
        },
        {
            "connection_id": str(CONNECTION_ID),
            "authorize_url": "https://auth.example/authorize",
            "state": "state",
            "expires_in": 0,
        },
    ],
)
async def test_malformed_gateway_oauth_start_fails_closed(
    oauth_response: dict[str, object],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"connections": []})
        return httpx.Response(201, json=oauth_response)

    app, gateway = _app(handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.post("/v1/connections/codex/oauth")
    await gateway.aclose()

    assert response.status_code == 502
    assert response.json()["code"] == "gateway_unavailable"
