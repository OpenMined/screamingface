from __future__ import annotations

from screamingface.plugins.aigw_gemini_backend.plugin import (
    AigwGeminiBackendPlugin,
    AigwGeminiBackendSettings,
)


def test_plugin_name_is_canonical() -> None:
    assert AigwGeminiBackendPlugin.name == "aigw-gemini-backend"


def test_plugin_grouped_under_gemini_product_tag() -> None:
    assert "product:gemini" in AigwGeminiBackendPlugin.tags
    assert "product:aigw" not in AigwGeminiBackendPlugin.tags


def test_plugin_dependency_chain() -> None:
    assert "aigw-base" in AigwGeminiBackendPlugin.depends
    assert "llm-base" in AigwGeminiBackendPlugin.depends
    assert "backend-api-base" in AigwGeminiBackendPlugin.depends


def test_plugin_conflicts_with_direct_gemini_backend() -> None:
    assert AigwGeminiBackendPlugin.conflicts == ["gemini-backend-api"]


def test_backend_call_paths_owns_canonical_gemini_path() -> None:
    assert AigwGeminiBackendPlugin.backend_call_paths == ["/gemini"]


def test_plugin_declares_gateway_provider() -> None:
    assert AigwGeminiBackendPlugin.gateway_provider == "gemini-cli"


def test_default_settings() -> None:
    settings = AigwGeminiBackendSettings()
    assert settings.default_model == "gemini-cli/gemini-2.5-flash"
    assert settings.gateway_url == "http://127.0.0.1:9105"
    assert settings.auth_profile == "default"
    assert settings.timeout_seconds == 300.0


def test_settings_env_prefix(monkeypatch) -> None:
    monkeypatch.setenv("SF_AIGW_GEMINI_BACKEND__GATEWAY_URL", "http://example:9999")
    monkeypatch.setenv("SF_AIGW_GEMINI_BACKEND__AUTH_PROFILE", "work")
    settings = AigwGeminiBackendSettings()
    assert settings.gateway_url == "http://example:9999"
    assert settings.auth_profile == "work"
