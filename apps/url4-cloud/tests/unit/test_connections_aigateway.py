from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from url4_cloud.connections.aigateway import AigatewayConnections
from url4_cloud.connections.port import (
    Caller,
    ConnectionBadResponse,
    ConnectionRejected,
    Connections,
    ConnectionTimeout,
    ConnectionUnavailable,
)

pytestmark = pytest.mark.asyncio

IDENTITY = {"X-User-Email": "alice@example.com"}
SECRET = "sk-or-v1-unit-secret"


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[AigatewayConnections, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def capture(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(
        base_url="http://aigateway.test",
        transport=httpx.MockTransport(capture),
    )
    return AigatewayConnections(client), seen


def _list(*rows: dict[str, object]) -> dict[str, object]:
    return {"connections": list(rows)}


def _row(
    *,
    connection_id: str = "00000000-0000-0000-0000-000000000001",
    status: str = "active",
    auth_type: str = "api_key",
    label: str = "screamingface",
) -> dict[str, object]:
    return {
        "id": connection_id,
        "account_id": "00000000-0000-0000-0000-000000000099",
        "provider": "openrouter",
        "label": label,
        "status": status,
        "auth_type": auth_type,
        "account": None,
        "credential_locator": {"service": "must-not-leak", "account": "default"},
        "created_at": "2026-07-31T00:00:00Z",
        "last_used_at": None,
        "last_refreshed_at": None,
        "error_message": None,
        "is_duplicate": False,
    }


async def test_adapter_satisfies_the_connection_port_and_advertises_openrouter() -> None:
    adapter, _ = _adapter(lambda _: httpx.Response(200, json=_list()))

    assert isinstance(adapter, Connections)
    assert await adapter.list(Caller(IDENTITY)) == (adapter.disconnected(),)


async def test_connected_state_is_sanitized_and_identity_is_forwarded() -> None:
    adapter, seen = _adapter(lambda _: httpx.Response(200, json=_list(_row())))

    (connection,) = await adapter.list(Caller(IDENTITY))

    assert connection.provider == "openrouter"
    assert connection.status == "connected"
    assert connection.auth_method == "api_key"
    assert connection.account_label is None
    assert seen[0].headers["X-User-Email"] == "alice@example.com"
    assert "authorization" not in seen[0].headers
    assert "credential_locator" not in repr(connection)


async def test_connect_creates_a_validated_connection_without_leaking_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_list())
        assert request.url.path == "/v1/oauth/connections/api-key"
        assert json.loads(request.content) == {
            "provider": "openrouter",
            "label": "screamingface",
            "api_key": SECRET,
        }
        return httpx.Response(201, json=_row())

    adapter, seen = _adapter(handler)

    connection = await adapter.connect(Caller(IDENTITY), "openrouter", SECRET)

    assert connection.status == "connected"
    assert SECRET not in repr(connection)
    assert SECRET not in str(seen[-1].url)


async def test_connect_replaces_the_single_existing_api_key_connection() -> None:
    existing = _row(label="research")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_list(existing))
        assert request.method == "PUT"
        assert request.url.path.endswith("/00000000-0000-0000-0000-000000000001/api-key")
        assert json.loads(request.content) == {"api_key": SECRET}
        return httpx.Response(200, json=existing)

    adapter, _ = _adapter(handler)

    assert (await adapter.connect(Caller(), "openrouter", SECRET)).status == "connected"


async def test_multiple_unmanaged_rows_leave_the_automatic_row_disconnected() -> None:
    rows = [
        _row(connection_id="00000000-0000-0000-0000-000000000001", label="one"),
        _row(connection_id="00000000-0000-0000-0000-000000000002", label="two"),
    ]

    adapter, _ = _adapter(lambda _: httpx.Response(200, json=_list(*rows)))

    assert await adapter.list(Caller()) == (adapter.disconnected(),)


async def test_disconnect_is_idempotent_and_removes_the_selected_connection() -> None:
    rows = [_row()]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_list(*rows))
        assert request.method == "DELETE"
        rows.clear()
        return httpx.Response(204)

    adapter, seen = _adapter(handler)

    assert (await adapter.disconnect(Caller(), "openrouter")).status == "not_connected"
    assert (await adapter.disconnect(Caller(), "openrouter")).status == "not_connected"
    assert [request.method for request in seen].count("DELETE") == 1


@pytest.mark.parametrize("status", [401, 403])
async def test_caller_authentication_rejection_is_typed(status: int) -> None:
    adapter, _ = _adapter(lambda _: httpx.Response(status, json={"detail": "private"}))

    with pytest.raises(ConnectionRejected):
        await adapter.list(Caller(IDENTITY))


async def test_invalid_key_failure_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_list())
        return httpx.Response(
            422,
            json={"detail": {"code": "invalid_api_key", "message": SECRET}},
        )

    adapter, _ = _adapter(handler)

    with pytest.raises(ConnectionRejected) as failure:
        await adapter.connect(Caller(), "openrouter", SECRET)

    assert SECRET not in str(failure.value)


async def test_malformed_upstream_response_is_typed() -> None:
    adapter, _ = _adapter(lambda _: httpx.Response(200, json={"connections": [_row(status="x")]}))

    with pytest.raises(ConnectionBadResponse):
        await adapter.list(Caller())


async def test_timeout_is_typed_and_secret_safe() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(SECRET, request=request)

    adapter, _ = _adapter(timeout)

    with pytest.raises(ConnectionTimeout) as failure:
        await adapter.connect(Caller(), "openrouter", SECRET)

    assert SECRET not in str(failure.value)


async def test_connection_refusal_is_reported_as_gateway_unavailable() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(SECRET, request=request)

    adapter, _ = _adapter(refused)

    with pytest.raises(ConnectionUnavailable) as failure:
        await adapter.list(Caller())

    assert failure.value.status == 503
    assert failure.value.detail == "AI Gateway is unavailable"
    assert SECRET not in str(failure.value)
