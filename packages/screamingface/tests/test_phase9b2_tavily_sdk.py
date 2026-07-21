from __future__ import annotations

import json

import httpx
import ipywidgets as widgets
import pytest

import screamingface as sf
from screamingface import _profile, connections


def _registry() -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": ["screamingface.recipe-result.v1"],
        "limits": {"max_request_target_bytes": 61440},
        "providers": [{"id": "tavily", "display_name": "Tavily", "auth_methods": ["api_key"]}],
        "models": [],
        "reducers": [{"id": "majority_vote", "route": "/reducers/majority-vote"}],
    }


def _record(status: str) -> dict[str, object]:
    return {
        "provider": "tavily",
        "status": status,
        "auth_method": "api_key" if status == "connected" else None,
        "account_label": None,
    }


@pytest.fixture
def tavily_engine(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, bytes]]:
    calls: list[tuple[str, str, bytes]] = []

    def response(request: httpx.Request) -> httpx.Response:  # noqa: PLR0911 - fake route table
        body = request.read()
        calls.append((request.method, request.url.path, body))
        if request.url.path == "/v1/connections" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "schema": "screamingface.connections.v1",
                    "connections": [_record("not_connected")],
                },
            )
        if request.url.path == "/v1/connections/tavily/api-key":
            return httpx.Response(200, json=_record("connected"))
        if request.url.path == "/v1/connections/tavily" and request.method == "GET":
            return httpx.Response(200, json=_record("connected"))
        if request.url.path == "/v1/connections/tavily" and request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    monkeypatch.setattr(_profile, "_get_text", lambda _path: json.dumps(_registry()))
    monkeypatch.setattr(connections, "_transport", httpx.MockTransport(response))
    sf.config(engine="http://127.0.0.1:4404")
    return calls


def _walk(widget: widgets.Widget) -> tuple[widgets.Widget, ...]:
    children = getattr(widget, "children", ())
    return (widget, *(item for child in children for item in _walk(child)))


def test_generic_sdk_and_panel_discover_tavily_without_a_special_case(tavily_engine) -> None:
    panel = sf.connect()
    widget = panel.widget()
    connection = sf.connect("tavily", api_key="tvly-sdk-private-secret")
    status = sf.connections.get("tavily")
    disconnected = sf.disconnect("tavily")

    assert panel.connections[0].provider == "tavily"
    assert any(
        isinstance(item, widgets.Button) and item.description == "Connect" for item in _walk(widget)
    )
    assert connection == sf.Connection(
        provider="tavily",
        display_name="Tavily",
        auth_methods=("api_key",),
        status="connected",
        auth_method="api_key",
        account_label=None,
    )
    assert status == connection
    assert disconnected.status == "not_connected"
    assert json.loads(tavily_engine[-3][2]) == {"api_key": "tvly-sdk-private-secret"}
    assert "tvly-sdk-private-secret" not in repr(connection)
