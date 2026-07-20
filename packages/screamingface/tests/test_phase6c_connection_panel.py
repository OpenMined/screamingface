from __future__ import annotations

import asyncio
import json
from html import unescape

import httpx
import ipywidgets as widgets
import pytest

import screamingface as sf
from screamingface import _profile, connections


def _registry() -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": ["screamingface.fusion-result.v1"],
        "limits": {"max_request_target_bytes": 61440},
        "providers": [
            {"id": "codex", "display_name": "OpenAI Codex", "auth_methods": ["oauth"]},
            {
                "id": "gemini",
                "display_name": "Google Gemini",
                "auth_methods": ["oauth", "api_key"],
            },
        ],
        "models": [
            {"id": "codex/gpt-5.5", "provider": "codex", "supported_tools": []},
            {"id": "gemini/2.5", "provider": "gemini", "supported_tools": []},
        ],
        "reducers": [{"id": "majority_vote", "route": "/reducers/majority-vote"}],
    }


class ConnectionEngine:
    def __init__(self) -> None:
        self.connected: dict[str, str | None] = {"codex": None, "gemini": None}
        self.calls: list[tuple[str, str, bytes]] = []
        self.reject_api_key = False

    def response(self, request: httpx.Request) -> httpx.Response:
        body = request.read()
        self.calls.append((request.method, request.url.path, body))
        path = request.url.path
        response: httpx.Response | None = None
        if path == "/v1/connections" and request.method == "GET":
            response = httpx.Response(
                200,
                json={
                    "schema": "screamingface.connections.v1",
                    "connections": [self._record("codex"), self._record("gemini")],
                },
            )
        if path == "/v1/connections/gemini/api-key" and request.method == "PUT":
            assert set(json.loads(body)) == {"api_key"}
            response = self._api_key_response()
        if path.endswith("/oauth") and request.method == "POST":
            provider = path.split("/")[3]
            response = httpx.Response(
                200,
                json={
                    "provider": provider,
                    "status": "pending",
                    "authorize_url": "https://auth.example/authorize?state=public-state",
                    "expires_in": 600,
                },
            )
        if path.startswith("/v1/connections/") and request.method == "GET":
            response = httpx.Response(200, json=self._record(path.split("/")[3]))
        if path.startswith("/v1/connections/") and request.method == "DELETE":
            self.connected[path.split("/")[3]] = None
            response = httpx.Response(204)
        if response is None:
            raise AssertionError(f"unexpected request {request.method} {path}")
        return response

    def _api_key_response(self) -> httpx.Response:
        if self.reject_api_key:
            return httpx.Response(
                401,
                json={
                    "schema": "screamingface.error.v1",
                    "code": "connection_needs_reauth",
                    "message": "Credential was rejected; reconnect this provider.",
                    "provider": "gemini",
                    "retryable": False,
                },
            )
        self.connected["gemini"] = "researcher<script>@example.com"
        return httpx.Response(200, json=self._record("gemini", "api_key"))

    def _record(self, provider: str, method: str | None = None) -> dict[str, object]:
        label = self.connected[provider]
        return {
            "provider": provider,
            "status": "connected" if label is not None else "not_connected",
            "auth_method": method or ("oauth" if label is not None else None),
            "account_label": label,
        }


@pytest.fixture
def connection_engine(monkeypatch: pytest.MonkeyPatch) -> ConnectionEngine:
    engine = ConnectionEngine()
    monkeypatch.setattr(_profile, "_get_text", lambda _path: json.dumps(_registry()))
    monkeypatch.setattr(connections, "_transport", httpx.MockTransport(engine.response))
    sf.config(engine="http://127.0.0.1:4404")
    return engine


def _walk(widget: widgets.Widget) -> tuple[widgets.Widget, ...]:
    children = getattr(widget, "children", ())
    return (widget, *(item for child in children for item in _walk(child)))


def _text(widget: widgets.Widget) -> str:
    values: list[str] = []
    for item in _walk(widget):
        for attribute in ("value", "description", "tooltip"):
            value = getattr(item, attribute, None)
            if isinstance(value, str):
                values.append(value)
    return "\n".join(values)


def test_argument_free_connect_returns_a_fresh_brand_panel(connection_engine) -> None:
    panel = sf.connect()

    assert not isinstance(panel, tuple)
    assert panel.engine == "http://127.0.0.1:4404"
    assert [item.provider for item in panel.connections] == ["codex", "gemini"]
    assert sf.connections.list()[0].provider == "codex"
    html = panel._repr_html_()
    assert "OpenAI Codex" in html
    assert "Google Gemini" in html
    assert "http://127.0.0.1:4404" in html
    assert "border-radius:0" in html.replace(" ", "")
    assert "linear-gradient" not in html
    assert "box-shadow:none" in html.replace(" ", "")
    assert "purple" not in html.lower()
    assert len([call for call in connection_engine.calls if call[1] == "/v1/connections"]) == 2


def test_panel_widget_is_accessible_and_does_not_open_oauth_implicitly(connection_engine) -> None:
    panel = sf.connect()
    widget = panel.widget()
    rendered = _text(widget)

    assert isinstance(widget, widgets.VBox)
    assert "Provider connections" in rendered
    assert "Connection credentials are stored by http://127.0.0.1:4404" in rendered
    assert "Connect with OAuth" in rendered
    assert not any(path.endswith("/oauth") for _, path, _ in connection_engine.calls)
    buttons = [item for item in _walk(widget) if isinstance(item, widgets.Button)]
    assert all(button.tooltip for button in buttons)
    assert all(button.layout.border == "1px solid var(--sf-line-2)" for button in buttons)


def test_masked_api_key_is_cleared_and_never_rendered(connection_engine) -> None:
    secret = "phase6c-super-secret-key"
    panel = sf.connect()
    widget = panel.widget()
    password = next(item for item in _walk(widget) if isinstance(item, widgets.Password))
    save = next(
        item
        for item in _walk(widget)
        if isinstance(item, widgets.Button) and item.description == "Save API key"
    )

    password.value = secret
    save.click()

    assert password.value == ""
    assert connection_engine.connected["gemini"] == "researcher<script>@example.com"
    assert secret not in repr(panel)
    assert secret not in panel._repr_html_()
    assert secret not in _text(widget)
    assert secret not in "\n".join(path for _, path, _ in connection_engine.calls)
    assert "researcher&lt;script&gt;@example.com" in panel._repr_html_()
    assert "<script>" not in panel._repr_html_()
    assert "researcher<script>@example.com" in unescape(panel._repr_html_())


def test_rejected_api_key_becomes_safe_inline_feedback(connection_engine) -> None:
    secret = "phase6c-rejected-super-secret"
    connection_engine.reject_api_key = True
    panel = sf.connect()
    widget = panel.widget()
    password = next(item for item in _walk(widget) if isinstance(item, widgets.Password))
    save = next(
        item
        for item in _walk(widget)
        if isinstance(item, widgets.Button) and item.description == "Save API key"
    )

    password.value = secret
    save.click()

    rendered = _text(widget)
    assert password.value == ""
    assert "Credential was rejected; reconnect this provider." in rendered
    assert secret not in rendered
    assert secret not in panel._repr_html_()


def test_oauth_requires_a_button_press_and_supports_cancel(connection_engine) -> None:
    panel = sf.connect()
    widget = panel.widget()
    oauth = next(
        item
        for item in _walk(widget)
        if isinstance(item, widgets.Button) and item.description == "Connect with OAuth"
    )

    oauth.click()

    assert any(path == "/v1/connections/codex/oauth" for _, path, _ in connection_engine.calls)
    assert "https://auth.example/authorize?state=public-state" in _text(widget)
    cancel = next(
        item
        for item in _walk(widget)
        if isinstance(item, widgets.Button) and item.description == "Cancel"
    )
    cancel.click()
    assert any(
        method == "DELETE" and path == "/v1/connections/codex"
        for method, path, _ in connection_engine.calls
    )


@pytest.mark.asyncio
async def test_widget_disposal_cancels_bounded_oauth_polling(connection_engine) -> None:
    panel = sf.connect()
    widget = panel.widget()
    oauth = next(
        item
        for item in _walk(widget)
        if isinstance(item, widgets.Button) and item.description == "Connect with OAuth"
    )

    oauth.click()
    tasks = tuple(panel._tasks.values())
    assert len(tasks) == 1

    widget.close()
    await asyncio.sleep(0)

    assert panel._tasks == {}
    assert tasks[0].cancelled() or tasks[0].done()
