from __future__ import annotations

from datetime import UTC, datetime

import pytest

import screamingface as sf
import screamingface.session as session_module
from screamingface.gateway import GatewayLogin, ProviderCapability
from screamingface.widgets import SetupPanel, login_panel, setup_panel


def test_static_setup_panel_is_visible_and_side_effect_free() -> None:
    session = sf.setup(mode="mock", static_widgets=True)

    panel = setup_panel(session, static=True)

    assert isinstance(panel, SetupPanel)
    assert panel.value is session
    assert "SIMULATION" in panel._repr_html_()
    assert "Connect providers" in panel._repr_html_()


def test_interactive_setup_panel_wraps_real_ipywidget() -> None:
    session = sf.setup(mode="mock")

    panel = setup_panel(session, static=False)

    assert panel.value is session
    assert panel.widget is not None
    bundle = panel._repr_mimebundle_()
    assert "application/vnd.jupyter.widget-view+json" in bundle


def test_static_setup_panel_mime_bundle_remains_renderable_html() -> None:
    panel = setup_panel(sf.setup(mode="mock", interactive=False), static=True)

    bundle = panel._repr_mimebundle_()

    assert bundle["text/plain"].startswith("SetupPanel")
    assert "SIMULATION" in bundle["text/html"]


class LoginGateway:
    def __init__(self, base_url: str, **_kwargs) -> None:
        self.base_url = base_url

    async def health(self) -> bool:
        return True

    async def login(self, username: str, password: str) -> GatewayLogin:
        assert password == "password"
        return GatewayLogin("jwt", datetime.now(UTC), username)

    async def me(self) -> dict[str, str]:
        return {"username": "reader"}

    async def list_connections(self) -> list:
        return []

    async def list_providers(self) -> list[ProviderCapability]:
        return [ProviderCapability("anthropic", ("api_key",), 2)]

    async def aclose(self) -> None:
        return None


def test_interactive_setup_can_authenticate_without_exposing_password(monkeypatch) -> None:
    monkeypatch.setattr(session_module, "AIGatewayClient", LoginGateway)

    panel = sf.setup(gateway="https://gateway.test", interactive=True)

    assert isinstance(panel, SetupPanel)
    assert panel.value is None
    panel.login("reader", "password")
    assert panel.value is sf.current_session()
    assert isinstance(panel.value, sf.Session)
    assert panel.value.mode == "live"
    assert "password" not in repr(panel)


def test_login_widget_is_compact_and_clear() -> None:
    panel = login_panel(lambda _username, _password: None)
    controls = panel.login_controls

    assert len(panel.widget.children) == 1
    assert controls["card"].layout.width == "420px"
    assert controls["card"].layout.max_width == "100%"
    assert controls["submit"].description == "Sign in"
    assert controls["submit"].layout.width == "100%"
    assert controls["username"].placeholder == "Your AI Gateway username"
    assert controls["password"].placeholder == "Your password"


def test_repeated_setup_reuses_authenticated_in_memory_session(monkeypatch) -> None:
    sf.reset_session()
    monkeypatch.setattr(session_module, "AIGatewayClient", LoginGateway)
    first = sf.setup(gateway="https://gateway.test", interactive=True)
    assert isinstance(first, SetupPanel)
    first.login("reader", "password")
    authenticated = first.value

    repeated = sf.setup(gateway="https://gateway.test", interactive=True)

    assert isinstance(repeated, SetupPanel)
    assert repeated.value is authenticated
    assert repeated.value is sf.current_session()


def test_live_widget_controls_use_session_api_and_clear_key() -> None:
    from test_production_hardening import ProductionGateway, _live_session

    gateway = ProductionGateway()
    panel = setup_panel(_live_session(gateway), static=False)
    controls = panel.provider_controls["anthropic"]
    controls["api_key"].value = "one-shot-secret"
    controls["connect"].click()
    assert controls["api_key"].value == ""
    assert gateway.api_keys_seen == ["one-shot-secret"]


def test_login_widget_callback_clears_password_on_error() -> None:
    def fail(_username: str, _password: str):
        raise RuntimeError("bad login")

    panel = login_panel(fail)
    username = panel.login_controls["username"]
    password = panel.login_controls["password"]
    button = panel.login_controls["submit"]
    status = panel.login_controls["status"]
    username.value = "reader"
    password.value = "secret"
    button.click()
    assert password.value == ""
    assert "bad login" in status.value


def test_notebook_gateway_unavailable_includes_startup_instructions(monkeypatch) -> None:
    class DownGateway(LoginGateway):
        async def health(self) -> bool:
            return False

    sf.reset_session()
    monkeypatch.setattr(session_module, "AIGatewayClient", DownGateway)

    with pytest.raises(sf.GatewayUnavailable) as caught:
        sf.setup(gateway="https://gateway.test", interactive=True)

    # INVARIANT: spec §4.1 — GatewayUnavailable always carries startup instructions,
    # in the notebook login path exactly as in the headless path.
    assert "Start apps/aigateway" in str(caught.value)
    assert "SCREAMINGFACE_GATEWAY_URL" in str(caught.value)
