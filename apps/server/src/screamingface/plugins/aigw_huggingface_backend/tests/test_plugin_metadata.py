from __future__ import annotations

from screamingface.plugins.aigw_huggingface_backend.plugin import (
    AigwHuggingfaceBackendPlugin,
    AigwHuggingfaceBackendSettings,
)


def test_plugin_name_is_canonical() -> None:
    assert AigwHuggingfaceBackendPlugin.name == "aigw-huggingface-backend"


def test_plugin_grouped_under_huggingface_product_tag() -> None:
    assert "product:huggingface" in AigwHuggingfaceBackendPlugin.tags
    assert "product:aigw" not in AigwHuggingfaceBackendPlugin.tags


def test_plugin_dependency_chain() -> None:
    assert "aigw-base" in AigwHuggingfaceBackendPlugin.depends
    assert "llm-base" in AigwHuggingfaceBackendPlugin.depends
    assert "backend-api-base" in AigwHuggingfaceBackendPlugin.depends


def test_plugin_has_no_legacy_conflict() -> None:
    # No legacy direct huggingface-backend-api plugin exists.
    assert AigwHuggingfaceBackendPlugin.conflicts == []


def test_backend_call_paths_owns_canonical_huggingface_path() -> None:
    assert AigwHuggingfaceBackendPlugin.backend_call_paths == ["/huggingface"]


def test_plugin_declares_gateway_provider() -> None:
    assert AigwHuggingfaceBackendPlugin.gateway_provider == "huggingface"


def test_plugin_declares_api_key_capability() -> None:
    # Drives the capability-driven desktop UI (api-key auth option).
    assert AigwHuggingfaceBackendPlugin.supports_api_key is True


def test_plugin_declares_no_oauth() -> None:
    # HF is api-key-only; the desktop must default to the API-key flow, not OAuth.
    assert AigwHuggingfaceBackendPlugin.supports_oauth is False


def test_default_settings() -> None:
    settings = AigwHuggingfaceBackendSettings()
    assert settings.default_model == "huggingface/deepseek-ai/DeepSeek-R1:novita"
    assert settings.gateway_url == "http://127.0.0.1:9105"
    assert settings.auth_profile == "default"
    assert settings.timeout_seconds == 300.0


def test_settings_env_prefix(monkeypatch) -> None:
    monkeypatch.setenv("SF_AIGW_HUGGINGFACE_BACKEND__AUTH_PROFILE", "work")
    settings = AigwHuggingfaceBackendSettings()
    assert settings.auth_profile == "work"
