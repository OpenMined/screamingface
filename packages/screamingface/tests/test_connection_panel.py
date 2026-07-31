from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import ipywidgets as widgets

import screamingface as sf

SECRET = "sk-or-v1-widget-secret"


class Engine:
    def __init__(self) -> None:
        self.connected = False
        self.reject = False
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911
        self.calls.append(request)
        row = {
            "object": "connection",
            "provider": "openrouter",
            "display_name": "OpenRouter",
            "auth_methods": ["api_key"],
            "status": "connected" if self.connected else "not_connected",
            "auth_method": "api_key" if self.connected else None,
            "account_label": None,
        }
        if request.method == "GET":
            return httpx.Response(200, json={"object": "list", "data": [row]})
        if request.method == "PUT":
            if self.reject:
                return httpx.Response(
                    401,
                    json={
                        "type": "about:blank",
                        "title": "Unauthorized",
                        "status": 401,
                        "detail": "private " + SECRET,
                    },
                )
            assert json.loads(request.content) == {"api_key": SECRET}
            self.connected = True
            return httpx.Response(
                200,
                json={**row, "status": "connected", "auth_method": "api_key"},
            )
        self.connected = False
        return httpx.Response(200, json={**row, "status": "not_connected", "auth_method": None})


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.Client:
    client = sf.Client(engine_url="https://engine.example")
    client._http.close()  # type: ignore[attr-defined]
    client._http = httpx.Client(  # type: ignore[attr-defined]
        base_url="https://engine.example",
        transport=httpx.MockTransport(handler),
    )
    return client


def _walk(widget: widgets.Widget) -> tuple[widgets.Widget, ...]:
    children = getattr(widget, "children", ())
    return (widget, *(item for child in children for item in _walk(child)))


def _buttons(widget: widgets.Widget) -> list[widgets.Button]:
    return [item for item in _walk(widget) if isinstance(item, widgets.Button)]


def _button(widget: widgets.Widget, description: str) -> widgets.Button:
    return next(item for item in _buttons(widget) if item.description == description)


def _password(widget: widgets.Widget) -> widgets.Password:
    return next(item for item in _walk(widget) if isinstance(item, widgets.Password))


def _text(widget: widgets.Widget) -> str:
    return "\n".join(
        value
        for item in _walk(widget)
        for attribute in ("value", "description", "tooltip")
        if isinstance((value := getattr(item, attribute, None)), str)
    )


def test_panel_keeps_the_full_collapsed_api_key_ui_and_only_one_openrouter_row() -> None:
    engine = Engine()
    client = _client(engine)
    panel = client.connect()
    root = panel.widget()

    assert [item.provider for item in panel.connections] == ["openrouter"]
    assert "Provider connections" in _text(root)
    assert "OpenRouter" in _text(root)
    assert "https://engine.example" in _text(root)
    assert [button.description for button in _buttons(root)] == ["Connect"]

    _button(root, "Connect").click()
    assert [button.description for button in _buttons(root)] == ["API key", "Cancel"]
    _button(root, "API key").click()
    password = _password(root)
    password.value = SECRET
    _button(root, "Save").click()

    assert password.value == ""
    assert [button.description for button in _buttons(root)] == ["Disconnect"]
    assert panel.connections[0].status == "connected"
    assert SECRET not in _text(root)
    assert SECRET not in panel._repr_html_()

    _button(root, "Disconnect").click()
    assert panel.connections[0].status == "not_connected"
    assert [button.description for button in _buttons(root)] == ["Connect"]
    root.close()
    client.close()


def test_panel_displays_safe_inline_errors_and_always_clears_the_password() -> None:
    engine = Engine()
    engine.reject = True
    client = _client(engine)
    root = client.connect().widget()

    _button(root, "Connect").click()
    _button(root, "API key").click()
    password = _password(root)
    password.value = SECRET
    _button(root, "Save").click()

    assert password.value == ""
    assert "Provider connection was rejected" in _text(root)
    assert SECRET not in _text(root)
    root.close()
    client.close()


def test_panel_retains_dormant_oauth_pending_and_cancel_controls() -> None:
    connection = sf.Connection(
        provider="future",
        display_name="Future Provider",
        auth_methods=("oauth", "api_key"),
        status="not_connected",
        auth_method=None,
        account_label=None,
    )

    class Connections:
        def list(self) -> tuple[sf.Connection, ...]:
            return (connection,)

    class FutureClient:
        engine_url = "https://engine.example"
        connections = Connections()

    panel = sf.ConnectionPanel(FutureClient())  # type: ignore[arg-type]
    root = panel.widget()

    _button(root, "Connect").click()
    assert [button.description for button in _buttons(root)] == ["OAuth", "API key", "Cancel"]

    pending = sf.Connection(
        provider="future",
        display_name="Future Provider",
        auth_methods=("oauth", "api_key"),
        status="pending",
        auth_method="oauth",
        account_label=None,
    )
    panel._connections = (pending,)  # type: ignore[attr-defined]
    panel._render_rows()  # type: ignore[attr-defined]
    assert [button.description for button in _buttons(root)] == ["Cancel"]
    root.close()
