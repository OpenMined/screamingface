from __future__ import annotations

from screamingface.plugins.aigw_codex_backend.plugin import (
    AigwCodexBackendPlugin,
    AigwCodexBackendSettings,
)


def test_plugin_name_is_canonical() -> None:
    assert AigwCodexBackendPlugin.name == "aigw-codex-backend"


def test_plugin_dependency_chain() -> None:
    assert "aigw-base" in AigwCodexBackendPlugin.depends
    assert "llm-base" in AigwCodexBackendPlugin.depends
    assert "backend-api-base" in AigwCodexBackendPlugin.depends


def test_plugin_conflicts_with_direct_codex_backend() -> None:
    assert AigwCodexBackendPlugin.conflicts == ["codex-backend-api"]


def test_backend_call_paths_owns_canonical_codex_path() -> None:
    assert AigwCodexBackendPlugin.backend_call_paths == ["/codex"]


def test_plugin_declares_gateway_provider() -> None:
    assert AigwCodexBackendPlugin.gateway_provider == "codex"


def test_default_settings() -> None:
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
