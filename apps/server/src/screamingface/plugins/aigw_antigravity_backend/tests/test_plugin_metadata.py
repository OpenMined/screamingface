from __future__ import annotations

from screamingface.plugins.aigw_antigravity_backend.plugin import (
    AigwAntigravityBackendPlugin,
    AigwAntigravityBackendSettings,
)


def test_plugin_name_is_canonical() -> None:
    assert AigwAntigravityBackendPlugin.name == "aigw-antigravity-backend"


def test_plugin_declares_gateway_provider() -> None:
    assert AigwAntigravityBackendPlugin.gateway_provider == "antigravity"


def test_backend_call_paths_owns_antigravity_path() -> None:
    assert AigwAntigravityBackendPlugin.backend_call_paths == ["/antigravity"]


def test_plugin_dependency_chain() -> None:
    assert "aigw-base" in AigwAntigravityBackendPlugin.depends
    assert "llm-base" in AigwAntigravityBackendPlugin.depends
    assert "backend-api-base" in AigwAntigravityBackendPlugin.depends


def test_depends_on_aigw_callback_for_scoped_bridge() -> None:
    # The OAuth callback bridge must activate ONLY when antigravity is enabled
    # (review #6). Declaring the dependency auto-activates aigw-callback when
    # this backend is active (registry.activate_all auto-adds discoverable
    # deps), instead of enabling it globally in sf.json — which would flip
    # gemini/codex/anthropic onto the loopback bridge in hosted mode.
    assert "aigw-callback" in AigwAntigravityBackendPlugin.depends


def test_callback_dependency_is_discoverable_so_auto_add_fires() -> None:
    # The depends-based auto-activation only works if aigw-callback is a
    # discoverable plugin (registry.activate_all auto-adds a missing dep ONLY
    # when it is in _discovered). This guard proves the precondition holds, so
    # enabling antigravity actually pulls in the callback bridge (review #6).
    from screamingface.core.registry import PluginRegistry

    discovered = PluginRegistry().discover()
    assert "aigw-callback" in discovered
    assert "aigw-antigravity-backend" in discovered


def test_does_not_conflict_with_gemini_backend() -> None:
    # Antigravity is a separate experimental provider; users compare/migrate.
    assert "aigw-gemini-backend" not in AigwAntigravityBackendPlugin.conflicts


def test_supports_api_key_is_false() -> None:
    # OAuth-only for v1 — Desktop must not offer a dead-end API-key UI.
    assert AigwAntigravityBackendPlugin.supports_api_key is False


def test_default_settings() -> None:
    settings = AigwAntigravityBackendSettings()
    assert settings.default_model == "antigravity/gemini-3.5-flash"
    assert settings.gateway_url == "http://127.0.0.1:9105"


def test_settings_env_prefix(monkeypatch) -> None:
    monkeypatch.setenv("SF_AIGW_ANTIGRAVITY_BACKEND__GATEWAY_URL", "http://example:9999")
    monkeypatch.setenv("SF_AIGW_ANTIGRAVITY_BACKEND__AUTH_PROFILE", "work")
    settings = AigwAntigravityBackendSettings()
    assert settings.gateway_url == "http://example:9999"
    assert settings.auth_profile == "work"
