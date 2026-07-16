from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pytest

import screamingface as sf
import screamingface.session as session_module
import screamingface.widgets as widgets_module
from screamingface.gateway import (
    AIGatewayClient,
    Completion,
    Connection,
    OAuthStart,
    ProviderCapability,
)
from screamingface.widgets import setup_panel


@pytest.mark.asyncio
async def test_sdk_supplies_temporary_auth_capabilities_for_gateway_models() -> None:
    rows = [
        {"id": "claude-sonnet-4-6", "owned_by": "anthropic"},
        {"id": "claude-haiku-4-5", "owned_by": "anthropic"},
        {"id": "antigravity/gemini-3-pro", "owned_by": "antigravity"},
        {"id": "codex/gpt-5.5", "owned_by": "codex"},
        {"id": "gemini-cli/gemini-2.5-pro", "owned_by": "gemini-cli"},
        {"id": "huggingface/model", "owned_by": "huggingface"},
        {"id": "ollama/qwen", "owned_by": "ollama"},
        {"id": "future/model", "owned_by": "future-provider"},
    ]
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"data": rows}))
    client = AIGatewayClient("https://gateway.test", token="jwt", transport=transport)

    providers = await client.list_providers()

    assert providers == [
        ProviderCapability("anthropic", ("api_key", "oauth"), 2),
        ProviderCapability("antigravity", ("oauth",), 1),
        ProviderCapability("codex", ("oauth",), 1),
        ProviderCapability("gemini-cli", ("api_key", "oauth"), 1),
        ProviderCapability("huggingface", ("api_key",), 1),
        ProviderCapability("ollama", ("none",), 1),
        ProviderCapability("future-provider", (), 1),
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_gateway_auth_capabilities_override_temporary_sdk_defaults() -> None:
    rows = [
        {
            "id": "future/model",
            "owned_by": "future-provider",
            "auth_methods": ["oauth"],
        }
    ]
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"data": rows}))
    client = AIGatewayClient("https://gateway.test", token="jwt", transport=transport)

    assert await client.list_providers() == [ProviderCapability("future-provider", ("oauth",), 1)]
    await client.aclose()


@dataclass
class OnboardingGateway:
    connections: list[Connection] = field(default_factory=list)
    created_keys: list[str] = field(default_factory=list)
    replaced_keys: list[str] = field(default_factory=list)
    oauth_starts: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    async def list_models(self) -> list[str]:
        return []

    async def list_providers(self) -> list[ProviderCapability]:
        return [
            ProviderCapability("anthropic", ("api_key", "oauth"), 2),
            ProviderCapability("gemini-cli", ("api_key", "oauth"), 4),
            ProviderCapability("huggingface", ("api_key",), 5),
            ProviderCapability("codex", ("oauth",), 5),
            ProviderCapability("ollama", ("none",), 1),
        ]

    async def list_connections(self) -> list[Connection]:
        return list(self.connections)

    async def create_api_key_connection(
        self, provider: str, label: str | None, api_key: str
    ) -> Connection:
        self.created_keys.append(api_key)
        connection = Connection("key-1", provider, label or "default", "active", "api_key")
        self.connections.append(connection)
        return connection

    async def replace_api_key_connection(self, connection_id: str, api_key: str) -> Connection:
        self.replaced_keys.append(api_key)
        return next(connection for connection in self.connections if connection.id == connection_id)

    async def start_oauth_connection(
        self, provider: str, label: str | None = None, redirect_uri: str | None = None
    ) -> OAuthStart:
        del redirect_uri
        self.oauth_starts.append(provider)
        self.connections.append(
            Connection("oauth-1", provider, label or "default", "pending", "oauth")
        )
        return OAuthStart("oauth-1", "https://provider.test/authorize", 600)

    async def delete_connection(self, connection_id: str) -> None:
        self.deleted.append(connection_id)
        self.connections = [row for row in self.connections if row.id != connection_id]

    async def get_connection(self, connection_id: str) -> Connection:
        return next(connection for connection in self.connections if connection.id == connection_id)

    async def aclose(self) -> None:
        return None

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        profile: str = "default",
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> Completion:
        del model, messages, profile, max_tokens, temperature
        return Completion("A")


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def _live_session(gateway: OnboardingGateway) -> sf.Session:
    session = sf.Session(mode="live", gateway_url="https://gateway.test", gateway=gateway)
    session_module._active = session
    return session


def test_session_supports_api_key_and_oauth_connections() -> None:
    gateway = OnboardingGateway()
    session = _live_session(gateway)

    created = session.connect("anthropic", api_key="first-secret")
    replaced = session.connect("anthropic", api_key="second-secret")

    assert created.id == replaced.id == "key-1"
    assert gateway.created_keys == ["first-secret"]
    assert gateway.replaced_keys == ["second-secret"]
    assert not hasattr(created, "api_key")
    with pytest.raises(ValueError, match="API key"):
        session.connect("anthropic", api_key="")
    oauth = session.connect_oauth("codex")
    assert oauth.authorize_url == "https://provider.test/authorize"
    assert gateway.oauth_starts == ["codex"]


def test_widget_uses_compact_provider_rows() -> None:
    gateway = OnboardingGateway()
    panel = setup_panel(_live_session(gateway), static=False)
    assert list(panel.provider_controls) == [
        "anthropic",
        "codex",
        "gemini-cli",
        "huggingface",
    ]
    provider_list = panel.widget.children[3]
    refresh = panel.widget.children[4]
    assert type(provider_list).__name__ == "VBox"
    assert provider_list.layout.overflow is None
    assert provider_list.layout.max_height is None
    assert refresh.description == "Check connection status"
    assert "Ollama" in panel.widget.children[2].value
    anthropic = panel.provider_controls["anthropic"]
    assert anthropic["card"].layout.border_bottom == "1px solid #e3e6e8"
    assert anthropic["details"].layout.display == "none"
    assert anthropic["open"].description == "Use API key"
    assert anthropic["oauth"].description == "Connect with OAuth"
    assert panel.provider_controls["huggingface"]["open"].description == "Use API key"
    assert panel.provider_controls["codex"]["oauth"].description == "Connect with OAuth"


def test_widget_renders_auth_methods_reported_by_gateway() -> None:
    gateway = OnboardingGateway()
    panel = setup_panel(_live_session(gateway), static=False)
    anthropic = panel.provider_controls["anthropic"]
    anthropic["open"].click()
    assert anthropic["details"].layout.display == "flex"
    assert anthropic["open"].layout.display == "none"
    assert anthropic["oauth"].layout.display == "none"
    anthropic["api_key"].value = "one-shot-secret"
    anthropic["connect"].click()

    assert anthropic["api_key"].value == ""
    assert gateway.created_keys == ["one-shot-secret"]
    assert "Connected via API key" in anthropic["status"].value
    assert "1</strong> providers connected" in panel.widget.children[1].value
    assert "oauth" in panel.provider_controls["anthropic"]
    assert anthropic["remove"].description == "Disconnect"
    assert anthropic["remove"].button_style == "danger"
    assert anthropic["remove"].disabled is False
    assert anthropic["remove"].layout.display == ""
    assert anthropic["details"].layout.display == "none"
    assert anthropic["open"].layout.display == "none"
    assert "oauth" in panel.provider_controls["codex"]
    assert "api_key" not in panel.provider_controls["codex"]
    assert "oauth" not in panel.provider_controls["huggingface"]


def test_widget_api_key_cancel_restores_inline_connection_choices() -> None:
    panel = setup_panel(_live_session(OnboardingGateway()), static=False)
    anthropic = panel.provider_controls["anthropic"]

    anthropic["open"].click()
    anthropic["api_key"].value = "not-submitted"
    anthropic["cancel_api"].click()

    assert anthropic["api_key"].value == ""
    assert anthropic["details"].layout.display == "none"
    assert anthropic["open"].layout.display == ""
    assert anthropic["oauth"].layout.display == ""


def test_widget_starts_oauth_and_surfaces_authorization_link() -> None:
    gateway = OnboardingGateway()
    session = _live_session(gateway)
    panel = setup_panel(session, static=False)

    codex = panel.provider_controls["codex"]
    codex["oauth"].click()

    assert gateway.oauth_starts == ["codex"]
    assert "Authorize Codex" in codex["status"].value
    assert "https://provider.test/authorize" in codex["status"].value
    assert "background:#1a73e8" in codex["status"].value
    assert codex["remove"].description == "Cancel connection"

    gateway.connections[0] = Connection("oauth-1", "codex", "default", "active", "oauth")
    panel._refresh_provider_cards()
    assert "Connected via OAuth" in codex["status"].value
    assert codex["remove"].description == "Disconnect"
    assert codex["oauth"].layout.display == "none"
    assert session.profiles == {"codex": "default"}


def test_widget_polls_pending_oauth_until_it_becomes_active(monkeypatch) -> None:
    class FakeIOLoop:
        def __init__(self) -> None:
            self.callbacks = []

        def call_later(self, _delay: float, callback) -> None:
            self.callbacks.append(callback)

    loop = FakeIOLoop()
    monkeypatch.setattr(widgets_module, "_notebook_io_loop", lambda: loop)
    gateway = OnboardingGateway()
    panel = setup_panel(_live_session(gateway), static=False)
    codex = panel.provider_controls["codex"]

    codex["oauth"].click()
    assert len(loop.callbacks) == 1

    gateway.connections[0] = Connection("oauth-1", "codex", "default", "active", "oauth")
    loop.callbacks.pop()()

    assert "Connected via OAuth" in codex["status"].value
    assert loop.callbacks == []


def test_widget_can_remove_api_key_connection() -> None:
    gateway = OnboardingGateway(
        connections=[Connection("key-1", "anthropic", "default", "active", "api_key")]
    )
    panel = setup_panel(_live_session(gateway), static=False)

    panel.provider_controls["anthropic"]["remove"].click()

    assert gateway.deleted == ["key-1"]
    assert panel.provider_controls["anthropic"]["status"].value == ""
    assert panel.provider_controls["anthropic"]["remove"].layout.display == "none"
    assert panel.provider_controls["anthropic"]["open"].layout.display == ""
    assert panel.provider_controls["anthropic"]["oauth"].layout.display == ""
    assert "0</strong> providers connected" in panel.widget.children[1].value
