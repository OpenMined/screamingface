"""Activation guard for the scoped OAuth callback bridge (review #6).

Proves that enabling ONLY aigw-antigravity-backend causes the registry to
auto-activate aigw-callback (via the plugin's `depends`), without aigw-callback
being in the global plugins list. This is the load-bearing behavior of the
scoped fix: the loopback bridge comes up when antigravity is on, and stays off
otherwise (so gemini/codex/anthropic OAuth-start is untouched).
"""

from __future__ import annotations

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig, ServerConfig

# aigw backends refuse to activate on a non-loopback SF host (LAN guard); use a
# loopback host so this mirrors a normal local run.
_LOOPBACK = ServerConfig(host="127.0.0.1")


def test_enabling_antigravity_auto_activates_callback_bridge() -> None:
    config = AppConfig(
        plugins=["aigw-antigravity-backend"],
        plugin_config={
            "aigw-antigravity-backend": {"gateway_url": "http://127.0.0.1:9105"},
        },
        server=_LOOPBACK,
    )
    app = create_app(config)

    active = app.state.plugins.active_plugins
    # The dependency chain (incl. aigw-callback) was auto-added + activated even
    # though only the backend was requested.
    assert "aigw-antigravity-backend" in active
    assert "aigw-callback" in active


def test_callback_bridge_not_active_without_antigravity() -> None:
    # Sanity: aigw-callback is NOT pulled in when antigravity is absent (so other
    # backends' OAuth-start behavior is unchanged — zero blast radius).
    config = AppConfig(plugins=["aigw-base"], plugin_config={}, server=_LOOPBACK)
    app = create_app(config)

    assert "aigw-callback" not in app.state.plugins.active_plugins
