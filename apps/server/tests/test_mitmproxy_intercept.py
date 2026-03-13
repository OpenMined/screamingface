"""Tests for the mitmproxy-intercept plugin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from screamingface.plugins.mitmproxy_intercept.addon import RewriteToScreamingFace
from screamingface.plugins.mitmproxy_intercept.plugin import (
    MitmproxyInterceptPlugin,
    MitmproxyInterceptSettings,
)
from screamingface.plugins.mitmproxy_intercept.state import (
    MitmproxyState,
    clear_state,
    is_stale,
    load_state,
    save_state,
)

# ---------------------------------------------------------------------------
# Settings defaults
# ---------------------------------------------------------------------------


def test_settings_defaults() -> None:
    settings = MitmproxyInterceptSettings()
    assert settings.domains == ["api.anthropic.com"]
    assert settings.proxy_port == 8888
    assert settings.mitmdump_path == "mitmdump"
    assert settings.auto_cleanup is True
    assert settings.trust_ca is True


# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------


def test_plugin_conflicts_with_claude_intercept() -> None:
    plugin = MitmproxyInterceptPlugin()
    assert "claude-intercept" in plugin.conflicts


def test_plugin_name() -> None:
    plugin = MitmproxyInterceptPlugin()
    assert plugin.name == "mitmproxy-intercept"


def test_plugin_no_system_deps() -> None:
    plugin = MitmproxyInterceptPlugin()
    assert plugin.system_deps == []


# ---------------------------------------------------------------------------
# State: is_stale()
# ---------------------------------------------------------------------------


def test_is_stale_no_state_file(tmp_path) -> None:
    with patch(
        "screamingface.plugins.mitmproxy_intercept.state.STATE_FILE",
        tmp_path / "nonexistent.json",
    ):
        assert is_stale() is False


def test_is_stale_process_dead(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    with patch("screamingface.plugins.mitmproxy_intercept.state.STATE_FILE", state_file):
        save_state(
            MitmproxyState(
                active=True,
                activated_at="2025-01-01T00:00:00",
                pid=999999999,  # very unlikely to exist
                proxy_port=8888,
                domains=["api.anthropic.com"],
            )
        )
        assert is_stale() is True


def test_is_stale_process_alive(tmp_path) -> None:
    import os

    state_file = tmp_path / "state.json"
    with patch("screamingface.plugins.mitmproxy_intercept.state.STATE_FILE", state_file):
        save_state(
            MitmproxyState(
                active=True,
                activated_at="2025-01-01T00:00:00",
                pid=os.getpid(),  # current process — definitely alive
                proxy_port=8888,
                domains=["api.anthropic.com"],
            )
        )
        assert is_stale() is False


def test_is_stale_inactive_state(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    with patch("screamingface.plugins.mitmproxy_intercept.state.STATE_FILE", state_file):
        save_state(
            MitmproxyState(
                active=False,
                activated_at="2025-01-01T00:00:00",
                pid=999999999,
                proxy_port=8888,
                domains=["api.anthropic.com"],
            )
        )
        assert is_stale() is False


# ---------------------------------------------------------------------------
# State: save/load/clear round-trip
# ---------------------------------------------------------------------------


def test_state_round_trip(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    with patch("screamingface.plugins.mitmproxy_intercept.state.STATE_FILE", state_file):
        original = MitmproxyState(
            active=True,
            activated_at="2025-01-01T00:00:00",
            pid=12345,
            proxy_port=8888,
            domains=["api.anthropic.com", "api.openai.com"],
        )
        save_state(original)
        loaded = load_state()
        assert loaded is not None
        assert loaded.pid == 12345
        assert loaded.domains == ["api.anthropic.com", "api.openai.com"]

        clear_state()
        assert load_state() is None


# ---------------------------------------------------------------------------
# Addon: RewriteToScreamingFace
# ---------------------------------------------------------------------------


def test_addon_rewrites_flow() -> None:
    addon = RewriteToScreamingFace()
    flow = MagicMock()
    flow.request.host = "api.anthropic.com"
    flow.request.port = 443
    flow.request.scheme = "https"

    addon.request(flow)

    # Default env vars: 127.0.0.1:8000, http
    assert flow.request.host == "127.0.0.1"
    assert flow.request.port == 8000
    assert flow.request.scheme == "http"
