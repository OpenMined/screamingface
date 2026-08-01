from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import screamingface as sf
from screamingface import _default_client

SECRET = "sk-or-v1-client-test-secret"


def _row(
    *,
    status: str = "not_connected",
    auth_method: str | None = None,
    auth_methods: list[str] | None = None,
) -> dict[str, object]:
    return {
        "object": "connection",
        "provider": "openrouter",
        "display_name": "OpenRouter",
        "auth_methods": auth_methods or ["api_key"],
        "status": status,
        "auth_method": auth_method,
        "account_label": None,
    }


def _list(row: dict[str, object] | None = None) -> dict[str, object]:
    return {"object": "list", "data": [row or _row()]}


def _sync_client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.Client:
    client = sf.Client(engine_url="https://engine.example")
    client._http.close()  # type: ignore[attr-defined]
    client._http = httpx.Client(  # type: ignore[attr-defined]
        base_url="https://engine.example",
        transport=httpx.MockTransport(handler),
    )
    return client


def _async_client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.AsyncClient:
    client = sf.AsyncClient(engine_url="https://engine.example")
    client._http = httpx.AsyncClient(  # type: ignore[attr-defined]
        base_url="https://engine.example",
        transport=httpx.MockTransport(handler),
    )
    return client


def test_explicit_client_lists_gets_connects_and_disconnects() -> None:
    connected = False
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal connected
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_list(_row(status="connected", auth_method="api_key"))
                if connected
                else _list(),
            )
        if request.method == "PUT":
            assert request.url.path == "/v1/connections/openrouter"
            assert json.loads(request.content) == {"api_key": SECRET}
            connected = True
            return httpx.Response(200, json=_row(status="connected", auth_method="api_key"))
        if request.method == "DELETE":
            connected = False
            return httpx.Response(200, json=_row())
        raise AssertionError(f"unexpected request {request.method}")

    with _sync_client(handler) as client:
        assert client.connections.list() == (
            sf.Connection(
                provider="openrouter",
                display_name="OpenRouter",
                auth_methods=("api_key",),
                status="not_connected",
                auth_method=None,
                account_label=None,
            ),
        )
        assert client.connections.get("openrouter").status == "not_connected"
        assert client.connect("openrouter", api_key=SECRET).status == "connected"
        assert client.connections.get("openrouter").status == "connected"
        assert client.disconnect("openrouter").status == "not_connected"

    assert SECRET not in repr(client.connections)
    assert all(SECRET not in str(request.url) for request in calls)


@pytest.mark.asyncio
async def test_async_client_has_the_same_connection_operations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_list())
        if request.method == "PUT":
            return httpx.Response(200, json=_row(status="connected", auth_method="api_key"))
        return httpx.Response(200, json=_row())

    async with _async_client(handler) as client:
        assert (await client.connections.list())[0].provider == "openrouter"
        assert (await client.connections.get("openrouter")).status == "not_connected"
        assert (await client.connect("openrouter", api_key=SECRET)).status == "connected"
        assert (await client.disconnect("openrouter")).status == "not_connected"


def test_module_functions_delegate_to_the_lazy_default_client(monkeypatch: Any) -> None:
    disconnected = sf.Connection(
        provider="openrouter",
        display_name="OpenRouter",
        auth_methods=("api_key",),
        status="not_connected",
        auth_method=None,
        account_label=None,
    )
    calls: list[tuple[str, object]] = []

    class Connections:
        def list(self) -> tuple[sf.Connection, ...]:
            calls.append(("list", None))
            return (disconnected,)

        def get(self, provider: str) -> sf.Connection:
            calls.append(("get", provider))
            return disconnected

    class FakeClient:
        engine_url = "https://engine.example"
        authenticated = True
        connections = Connections()

        def connect(self, provider: str, *, api_key: str) -> sf.Connection:
            calls.append(("connect", (provider, api_key)))
            return disconnected

        def disconnect(self, provider: str) -> sf.Connection:
            calls.append(("disconnect", provider))
            return disconnected

    monkeypatch.setattr(_default_client, "_client", FakeClient())

    assert sf.connections.list() == (disconnected,)
    assert sf.connections.get("openrouter") == disconnected
    assert sf.connect("openrouter", api_key=SECRET) == disconnected
    assert sf.disconnect("openrouter") == disconnected
    panel = sf.connect()
    assert panel.engine == "https://engine.example"
    assert panel.connections == (disconnected,)
    assert [name for name, _ in calls] == ["list", "get", "connect", "disconnect", "list"]

    monkeypatch.setattr(_default_client, "_client", None)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"object": "wrong", "data": []},
        {"object": "list", "data": "wrong"},
        {"object": "list", "data": [_row(status="unknown")]},
        {"object": "list", "data": [_row(), _row()]},
        {"object": "list", "data": [{**_row(), "private": "must reject"}]},
    ],
)
def test_connection_catalog_rejects_malformed_payloads(payload: object) -> None:
    client = _sync_client(lambda _: httpx.Response(200, json=payload))

    with client, pytest.raises(sf.ProviderConnectionError) as failure:
        client.connections.list()

    assert failure.value.code == "invalid_connection_response"


def test_engine_failures_are_safe_and_typed() -> None:
    client = _sync_client(
        lambda _: httpx.Response(
            401,
            json={
                "type": "about:blank",
                "title": "Unauthorized",
                "status": 401,
                "detail": "upstream body " + SECRET,
            },
        )
    )

    with client, pytest.raises(sf.ProviderConnectionError) as failure:
        client.connect("openrouter", api_key=SECRET)

    assert failure.value.status == 401
    assert failure.value.code == "connection_rejected"
    assert SECRET not in str(failure.value)


def test_unreachable_engine_has_a_dedicated_actionable_error() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private socket detail", request=request)

    client = _sync_client(unreachable)

    with client, pytest.raises(sf.EngineUnavailableError) as failure:
        client.connections.list()

    assert failure.value.engine_url == "https://engine.example"
    assert failure.value.code == "engine_unreachable"
    assert "Check that the configured SF Engine is running" in failure.value.user_message
    assert "private socket detail" not in failure.value.user_message


@pytest.mark.asyncio
async def test_async_unreachable_engine_has_the_same_actionable_error() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private socket detail", request=request)

    async with _async_client(unreachable) as client:
        with pytest.raises(sf.EngineUnavailableError) as failure:
            await client.connections.list()

    assert failure.value.engine_url == "https://engine.example"
    assert "Check that the configured SF Engine is running" in failure.value.user_message


def test_connection_values_are_immutable_and_strict() -> None:
    value = sf.Connection(
        provider="openrouter",
        display_name="OpenRouter",
        auth_methods=("api_key",),
        status="connected",
        auth_method="api_key",
        account_label=None,
    )

    with pytest.raises(AttributeError):
        value.status = "error"  # type: ignore[misc]
    with pytest.raises(ValueError, match="not advertised"):
        sf.Connection("openrouter", "OpenRouter", ("api_key",), "connected", "oauth", None)
    with pytest.raises(ValueError, match="non-empty"):
        _sync_client(lambda _: httpx.Response(200, json=_row())).connect(
            "openrouter",
            api_key=" ",
        )


def test_provider_keys_require_https_outside_loopback() -> None:
    client = sf.Client(engine_url="http://engine.example")

    with client, pytest.raises(sf.ProviderConnectionError) as failure:
        client.connect("openrouter", api_key=SECRET)

    assert failure.value.code == "secure_transport_required"
