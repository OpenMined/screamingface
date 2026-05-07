"""Plugin metadata + settings construction tests."""

from __future__ import annotations

from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)


def test_plugin_name_is_canonical() -> None:
    assert AigwClaudeBackendPlugin.name == "aigw-claude-backend"


def test_plugin_grouped_under_claude_product_tag() -> None:
    """UI groups by `product:` tag — claude backends belong with the legacy
    claude-backend-api in the 'claude' category, not 'aigw'."""
    assert "product:claude" in AigwClaudeBackendPlugin.tags
    assert "product:aigw" not in AigwClaudeBackendPlugin.tags


def test_plugin_dependency_chain() -> None:
    assert "aigw-base" in AigwClaudeBackendPlugin.depends
    assert "llm-base" in AigwClaudeBackendPlugin.depends
    assert "backend-api-base" in AigwClaudeBackendPlugin.depends


def test_plugin_conflicts_with_legacy_claude_backend() -> None:
    """aigw-claude-backend takes over /claude; cannot coexist with the legacy direct-API plugin."""
    assert AigwClaudeBackendPlugin.conflicts == ["claude-backend-api"]


def test_backend_call_paths_owns_canonical_claude_path() -> None:
    """Same path as claude-backend-api so url4 specs route through the gateway transparently."""
    assert AigwClaudeBackendPlugin.backend_call_paths == ["/claude"]


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
