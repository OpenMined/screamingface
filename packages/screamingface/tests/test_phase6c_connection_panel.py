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
        "response_schemas": [
            "screamingface.recipe-result.v1",
            "screamingface.case-grade.v1",
            "screamingface.report.v1",
        ],
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
            {"id": "gemini/2.5-flash", "provider": "gemini", "supported_tools": []},
        ],
        "benchmarks": [],
        "reducers": [{"id": "majority_vote", "route": "/reducers/majority-vote/1"}],
    }


class ConnectionEngine:
    def __init__(self) -> None:
        self.connected: dict[str, str | None] = {"codex": None, "gemini": None}
        self.pending: set[str] = set()
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
            self.pending.add(provider)
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
            provider = path.split("/")[3]
            self.connected[provider] = None
            self.pending.discard(provider)
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
        status = (
            "pending" if provider in self.pending else "connected" if label else "not_connected"
        )
        return {
            "provider": provider,
            "status": status,
            "auth_method": method
            or ("oauth" if label is not None or provider in self.pending else None),
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


def _buttons(widget: widgets.Widget) -> list[widgets.Button]:
    return [item for item in _walk(widget) if isinstance(item, widgets.Button)]


def _button(widget: widgets.Widget, description: str, *, occurrence: int = 0) -> widgets.Button:
    matches = [item for item in _buttons(widget) if item.description == description]
    return matches[occurrence]


def test_argument_free_connect_returns_a_fresh_brand_panel(connection_engine) -> None:
    panel = sf.connect()

    assert not isinstance(panel, tuple)
    assert panel.engine == "http://127.0.0.1:4404"
    assert [item.provider for item in panel.connections] == ["codex", "gemini"]
    assert sf.connections.list()[0].provider == "codex"
    html = panel._repr_html_()
    assert "class='sf-ui sf-connections'" in html
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
    assert "Engine · http://127.0.0.1:4404" in rendered
    assert [button.description for button in _buttons(widget)] == ["Connect", "Connect"]
    assert "OAuth" not in rendered
    assert "API key" not in rendered
    assert not any(isinstance(item, widgets.Password) for item in _walk(widget))
    assert not any(path.endswith("/oauth") for _, path, _ in connection_engine.calls)
    assert all(button.tooltip for button in _buttons(widget))


def test_masked_api_key_is_cleared_and_never_rendered(connection_engine) -> None:
    secret = "phase6c-super-secret-key"
    panel = sf.connect()
    widget = panel.widget()
    _button(widget, "Connect", occurrence=1).click()
    _button(widget, "API key").click()
    password = next(item for item in _walk(widget) if isinstance(item, widgets.Password))
    save = _button(widget, "Save")

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
    _button(widget, "Connect", occurrence=1).click()
    _button(widget, "API key").click()
    password = next(item for item in _walk(widget) if isinstance(item, widgets.Password))
    save = _button(widget, "Save")

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

    _button(widget, "Connect").click()
    assert not any(path.endswith("/oauth") for _, path, _ in connection_engine.calls)
    oauth = _button(widget, "OAuth")

    oauth.click()

    assert any(path == "/v1/connections/codex/oauth" for _, path, _ in connection_engine.calls)
    assert "https://auth.example/authorize?state=public-state" in _text(widget)
    assert "Authorize" in _text(widget)
    cancel = _button(widget, "Cancel")
    cancel.click()
    assert any(
        method == "DELETE" and path == "/v1/connections/codex"
        for method, path, _ in connection_engine.calls
    )


@pytest.mark.asyncio
async def test_widget_disposal_cancels_bounded_oauth_polling(connection_engine) -> None:
    panel = sf.connect()
    widget = panel.widget()

    _button(widget, "Connect").click()
    oauth = _button(widget, "OAuth")

    oauth.click()
    tasks = tuple(panel._tasks.values())
    assert len(tasks) == 1

    widget.close()
    await asyncio.sleep(0)

    assert panel._tasks == {}
    assert tasks[0].cancelled() or tasks[0].done()


def test_connect_reveals_only_supported_methods_and_cancel_restores_row(connection_engine) -> None:
    panel = sf.connect()
    widget = panel.widget()
    rows = widget.children[2]

    assert isinstance(rows, widgets.VBox)
    assert len(rows.children) == 2
    assert all(row.layout.height == "48px" for row in rows.children)

    _button(widget, "Connect", occurrence=1).click()

    assert [button.description for button in _buttons(rows.children[0])] == ["Connect"]
    assert [button.description for button in _buttons(rows.children[1])] == [
        "OAuth",
        "API key",
        "Cancel",
    ]
    assert not any(isinstance(item, widgets.Password) for item in _walk(widget))

    _button(rows.children[1], "Cancel").click()

    assert [button.description for button in _buttons(widget)] == ["Connect", "Connect"]
    assert not any(path.endswith("/oauth") for _, path, _ in connection_engine.calls)


def test_api_key_editor_is_inline_cancellable_and_mutation_free(connection_engine) -> None:
    panel = sf.connect()
    widget = panel.widget()

    _button(widget, "Connect", occurrence=1).click()
    _button(widget, "API key").click()

    assert len([item for item in _walk(widget) if isinstance(item, widgets.Password)]) == 1
    assert [button.description for button in _buttons(widget)][-2:] == ["Save", "Cancel"]
    _button(widget, "Cancel").click()

    assert not any(isinstance(item, widgets.Password) for item in _walk(widget))
    assert not any(path.endswith("/api-key") for _, path, _ in connection_engine.calls)


def test_connected_provider_stays_compact_with_only_disconnect(connection_engine) -> None:
    connection_engine.connected["gemini"] = "researcher@example.com"
    panel = sf.connect()
    widget = panel.widget()
    rows = widget.children[2]

    assert [button.description for button in _buttons(rows.children[0])] == ["Connect"]
    assert [button.description for button in _buttons(rows.children[1])] == ["Disconnect"]
    assert "researcher@example.com" in _text(rows.children[1])
    assert all(row.layout.height == "48px" for row in rows.children)


def test_widget_uses_one_unframed_shell_with_only_row_dividers(connection_engine) -> None:
    panel = sf.connect()
    widget = panel.widget()
    header = widget.children[0]

    assert "sf-connections" in widget._dom_classes
    assert "class='sf-connections sf-connections__head'" not in header.value
    assert "border:0" in header.value.replace(" ", "")
    assert "box-shadow:none" in header.value.replace(" ", "")


def test_connected_account_follows_provider_name_in_parentheses(connection_engine) -> None:
    connection_engine.connected["gemini"] = "researcher@example.com"
    panel = sf.connect()
    widget = panel.widget()
    row = widget.children[2].children[1]
    meta = next(item for item in _walk(row) if isinstance(item, widgets.HTML))

    assert (
        "<span class='sf-connections__provider'>Google Gemini "
        "<span class='sf-connections__account'>(researcher@example.com)</span></span>" in meta.value
    )
    assert meta.value.index("researcher@example.com") < meta.value.index("sf-connections__status")


def test_fresh_panel_exposes_cancel_for_engine_persisted_pending_oauth(connection_engine) -> None:
    initiating_panel = sf.connect()
    initiating_widget = initiating_panel.widget()
    _button(initiating_widget, "Connect").click()
    _button(initiating_widget, "OAuth").click()

    fresh_panel = sf.connect()
    fresh_widget = fresh_panel.widget()
    codex_row = fresh_widget.children[2].children[0]

    assert "pending" in _text(codex_row).lower()
    assert [button.description for button in _buttons(codex_row)] == ["Cancel"]
    assert "Authorize" not in _text(codex_row)

    _button(codex_row, "Cancel").click()

    refreshed_row = fresh_widget.children[2].children[0]
    assert [button.description for button in _buttons(refreshed_row)] == ["Connect"]
    assert any(
        method == "DELETE" and path == "/v1/connections/codex"
        for method, path, _ in connection_engine.calls
    )
