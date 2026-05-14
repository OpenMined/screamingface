from __future__ import annotations

from screamingface.plugins.aigw_codex_backend.plugin import (
    AigwCodexBackendPlugin,
    AigwCodexBackendSettings,
)


def test_plugin_metadata() -> None:
    assert AigwCodexBackendPlugin.name == "aigw-codex-backend"
    assert AigwCodexBackendPlugin.backend_call_paths == ["/codex"]
    assert AigwCodexBackendPlugin.conflicts == ["codex-backend-api"]
    assert AigwCodexBackendPlugin.gateway_provider == "codex"
    assert AigwCodexBackendPlugin.auth_kind == "import"
    assert "product:openai" in AigwCodexBackendPlugin.tags
    assert "aigw-base" in AigwCodexBackendPlugin.depends
    assert "llm-base" in AigwCodexBackendPlugin.depends
    assert "backend-api-base" in AigwCodexBackendPlugin.depends
    assert AigwCodexBackendPlugin.settings_class is AigwCodexBackendSettings


def test_default_model() -> None:
    settings = AigwCodexBackendSettings()
    assert settings.default_model == "codex/gpt-5.4-mini"
    assert settings.gateway_url == "http://127.0.0.1:9105"
    assert settings.auth_profile == "default"
    assert settings.timeout_seconds == 300.0


def test_settings_env_prefix(monkeypatch) -> None:
    monkeypatch.setenv("SF_AIGW_CODEX_BACKEND__GATEWAY_URL", "http://example:9999")
    monkeypatch.setenv("SF_AIGW_CODEX_BACKEND__AUTH_PROFILE", "work")

    settings = AigwCodexBackendSettings()

    assert settings.gateway_url == "http://example:9999"
    assert settings.auth_profile == "work"
