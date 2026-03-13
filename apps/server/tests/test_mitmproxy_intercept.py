"""Tests for the mitmproxy-intercept plugin."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from screamingface.core.frontend import FrontendEntry, FrontendRegistry
from screamingface.plugins.mitmproxy_intercept.addon import RouteToFrontend
from screamingface.plugins.mitmproxy_intercept.plugin import (
    MitmproxyInterceptPlugin,
    MitmproxyInterceptSettings,
    RoutingRule,
    _resolve_rules,
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
    assert settings.rules == []
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
        )
        save_state(original)
        loaded = load_state()
        assert loaded is not None
        assert loaded.pid == 12345

        clear_state()
        assert load_state() is None


# ---------------------------------------------------------------------------
# Addon: RouteToFrontend
# ---------------------------------------------------------------------------


def test_addon_routes_by_domain(tmp_path) -> None:
    """Addon routes to the correct frontend based on domain mapping."""
    frontends_file = tmp_path / "frontends.json"
    mapping = {
        "api.anthropic.com": {"host": "127.0.0.1", "port": 8081, "scheme": "http"},
        "api.openai.com": {"host": "127.0.0.1", "port": 8082, "scheme": "http"},
    }
    frontends_file.write_text(json.dumps(mapping))

    with patch(
        "screamingface.plugins.mitmproxy_intercept.addon.FRONTENDS_FILE",
        str(frontends_file),
    ):
        addon = RouteToFrontend()

    flow = MagicMock()
    flow.request.pretty_host = "api.anthropic.com"
    flow.request.port = 443
    flow.request.scheme = "https"

    addon.request(flow)

    assert flow.request.host == "127.0.0.1"
    assert flow.request.port == 8081
    assert flow.request.scheme == "http"


def test_addon_fallback_when_no_mapping() -> None:
    """Addon falls back to SF_HOST/SF_PORT/SF_SCHEME for unmapped domains."""
    addon = RouteToFrontend()
    addon.domain_map = {}  # no frontends registered

    flow = MagicMock()
    flow.request.pretty_host = "unknown.example.com"
    flow.request.port = 443
    flow.request.scheme = "https"

    addon.request(flow)

    # Falls back to env var defaults
    assert flow.request.host == "127.0.0.1"
    assert flow.request.port == 8000
    assert flow.request.scheme == "http"


def test_addon_fallback_no_frontends_file() -> None:
    """Addon gracefully handles missing frontends.json."""
    with patch(
        "screamingface.plugins.mitmproxy_intercept.addon.FRONTENDS_FILE",
        "/nonexistent/path/frontends.json",
    ):
        addon = RouteToFrontend()

    assert addon.domain_map == {}

    flow = MagicMock()
    flow.request.pretty_host = "api.anthropic.com"
    addon.request(flow)
    assert flow.request.host == "127.0.0.1"
    assert flow.request.port == 8000


# ---------------------------------------------------------------------------
# Routing rules: _resolve_rules()
# ---------------------------------------------------------------------------


def _make_registry(*entries: FrontendEntry) -> FrontendRegistry:
    """Helper — build a FrontendRegistry with pre-registered entries (no disk I/O)."""
    reg = FrontendRegistry()
    for e in entries:
        reg._entries[e.plugin_name] = e
    return reg


def test_resolve_rules_maps_domain_to_frontend() -> None:
    """An explicit rule resolves to the frontend's host:port."""
    registry = _make_registry(
        FrontendEntry(plugin_name="claude-frontend", domains=["api.anthropic.com"], port=9101),
    )
    rules = [RoutingRule(domain="api.anthropic.com", frontend="claude-frontend")]
    result = _resolve_rules(rules, registry)
    assert result == {
        "api.anthropic.com": {"host": "127.0.0.1", "port": 9101, "scheme": "http"},
    }


def test_resolve_rules_skips_unknown_frontend() -> None:
    """Rules referencing unregistered frontends are skipped with a warning."""
    registry = _make_registry()  # empty
    rules = [RoutingRule(domain="api.openai.com", frontend="openai-frontend")]
    result = _resolve_rules(rules, registry)
    assert result == {}


def test_resolve_rules_remaps_domain() -> None:
    """A rule can point an arbitrary domain to a registered frontend."""
    registry = _make_registry(
        FrontendEntry(plugin_name="claude-frontend", domains=["api.anthropic.com"], port=9101),
    )
    rules = [RoutingRule(domain="custom.example.com", frontend="claude-frontend")]
    result = _resolve_rules(rules, registry)
    assert result == {
        "custom.example.com": {"host": "127.0.0.1", "port": 9101, "scheme": "http"},
    }


def test_merged_rules_override_auto_discovery() -> None:
    """When the same domain appears in both auto-discovery and rules, rules win."""
    registry = _make_registry(
        FrontendEntry(plugin_name="claude-frontend", domains=["api.anthropic.com"], port=9101),
        FrontendEntry(plugin_name="alt-frontend", domains=["api.anthropic.com"], port=9200),
    )
    rules = [RoutingRule(domain="api.anthropic.com", frontend="alt-frontend")]

    auto_map = registry.get_domain_map()  # last writer wins → alt-frontend already
    rules_map = _resolve_rules(rules, registry)
    merged = {**auto_map, **rules_map}

    # Rules overlay: alt-frontend's port should win
    assert merged["api.anthropic.com"]["port"] == 9200


def test_merged_includes_auto_discovered_gaps() -> None:
    """Domains only in auto-discovery (not covered by rules) survive the merge."""
    registry = _make_registry(
        FrontendEntry(plugin_name="claude-frontend", domains=["api.anthropic.com"], port=9101),
        FrontendEntry(plugin_name="gemini-frontend", domains=["api.gemini.com"], port=9102),
    )
    rules = [RoutingRule(domain="api.anthropic.com", frontend="claude-frontend")]

    auto_map = registry.get_domain_map()
    rules_map = _resolve_rules(rules, registry)
    merged = {**auto_map, **rules_map}

    assert "api.anthropic.com" in merged
    assert "api.gemini.com" in merged
    assert merged["api.gemini.com"]["port"] == 9102


def test_settings_with_rules() -> None:
    """Pydantic parses rules from a dict."""
    settings = MitmproxyInterceptSettings(
        rules=[{"domain": "api.anthropic.com", "frontend": "claude-frontend"}],  # type: ignore[list-item]
    )
    assert len(settings.rules) == 1
    assert settings.rules[0].domain == "api.anthropic.com"
    assert settings.rules[0].frontend == "claude-frontend"
