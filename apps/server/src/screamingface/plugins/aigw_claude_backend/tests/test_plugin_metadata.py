"""Plugin metadata + settings construction tests."""

from __future__ import annotations

from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)


def test_plugin_name_is_canonical() -> None:
    assert AigwClaudeBackendPlugin.name == "aigw-claude-backend"


def test_plugin_dependency_chain() -> None:
    assert "aigw-base" in AigwClaudeBackendPlugin.depends
    assert "llm-base" in AigwClaudeBackendPlugin.depends
    assert "backend-api-base" in AigwClaudeBackendPlugin.depends


def test_plugin_no_conflicts() -> None:
    """aigw-claude-backend coexists with claude-backend-api."""
    assert AigwClaudeBackendPlugin.conflicts == []


def test_backend_call_paths() -> None:
    assert AigwClaudeBackendPlugin.backend_call_paths == ["/aigw-claude"]


def test_default_settings() -> None:
    s = AigwClaudeBackendSettings()
    assert s.default_model == "anthropic/claude-sonnet-4-5"
    assert s.gateway_url == "http://127.0.0.1:9105"
    assert s.auth_profile == "default"
    assert s.timeout_seconds == 300.0


def test_settings_env_prefix(monkeypatch) -> None:
    monkeypatch.setenv("SF_AIGW_CLAUDE_BACKEND__GATEWAY_URL", "http://example:9999")
    monkeypatch.setenv("SF_AIGW_CLAUDE_BACKEND__AUTH_PROFILE", "work")
    s = AigwClaudeBackendSettings()
    assert s.gateway_url == "http://example:9999"
    assert s.auth_profile == "work"
