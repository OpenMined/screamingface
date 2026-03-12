"""Tests for the plugin registry."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from screamingface.core.registry import PluginRegistry
from screamingface.plugin import Plugin


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_has_registries(client: TestClient) -> None:
    from fastapi import FastAPI

    app = client.app
    assert isinstance(app, FastAPI)
    assert hasattr(app.state, "hooks")
    assert hasattr(app.state, "classes")
    assert hasattr(app.state, "routes")
    assert hasattr(app.state, "plugins")
    assert hasattr(app.state, "config")


# --- Preflight / skip tests ---


class _PassPlugin(Plugin):
    name = "pass-plugin"

    def preflight(self) -> tuple[bool, str]:
        return True, ""

    def setup(self, **kwargs):  # type: ignore[override]
        pass


class _FailPlugin(Plugin):
    name = "fail-plugin"

    def preflight(self) -> tuple[bool, str]:
        return False, "not ready"

    def setup(self, **kwargs):  # type: ignore[override]
        pass


class _NoDepsPlugin(Plugin):
    name = "no-deps"
    system_deps = ["__nonexistent_tool_xyz__"]

    def setup(self, **kwargs):  # type: ignore[override]
        pass


class _DependentPlugin(Plugin):
    name = "dependent"
    depends = ["fail-plugin"]

    def setup(self, **kwargs):  # type: ignore[override]
        pass


class _AlphaPlugin(Plugin):
    name = "alpha"
    conflicts = ["beta"]

    def setup(self, **kwargs):  # type: ignore[override]
        pass


class _BetaPlugin(Plugin):
    name = "beta"
    conflicts = ["alpha"]

    def setup(self, **kwargs):  # type: ignore[override]
        pass


def test_preflight_pass() -> None:
    reg = PluginRegistry()
    plugin = _PassPlugin()
    reg.activate(plugin)
    assert "pass-plugin" in reg.active_plugins


def test_preflight_fail_skips(caplog: pytest.LogCaptureFixture) -> None:
    reg = PluginRegistry()
    plugin = _FailPlugin()
    with caplog.at_level(logging.WARNING):
        reg.activate(plugin)
    assert "fail-plugin" not in reg.active_plugins
    assert "not ready" in caplog.text


def test_system_deps_missing_skips(caplog: pytest.LogCaptureFixture) -> None:
    reg = PluginRegistry()
    plugin = _NoDepsPlugin()
    with caplog.at_level(logging.WARNING):
        reg.activate(plugin)
    assert "no-deps" not in reg.active_plugins
    assert "__nonexistent_tool_xyz__" in caplog.text


def test_depends_missing_skips(caplog: pytest.LogCaptureFixture) -> None:
    reg = PluginRegistry()
    plugin = _DependentPlugin()
    with caplog.at_level(logging.WARNING):
        reg.activate(plugin)
    assert "dependent" not in reg.active_plugins
    assert "fail-plugin" in caplog.text


def test_cascade_skip(caplog: pytest.LogCaptureFixture) -> None:
    """If plugin A is skipped, plugin B that depends on A is also skipped."""
    reg = PluginRegistry()

    # Register both plugins as discovered so activate_all can load them
    reg._discovered["fail-plugin"] = _FailPlugin
    reg._discovered["dependent"] = _DependentPlugin

    with caplog.at_level(logging.WARNING):
        activated = reg.activate_all(["fail-plugin", "dependent"])

    assert len(activated) == 0
    assert "fail-plugin" not in reg.active_plugins
    assert "dependent" not in reg.active_plugins


def test_conflict_skips(caplog: pytest.LogCaptureFixture) -> None:
    """If plugin A conflicts with active plugin B, A is skipped."""
    reg = PluginRegistry()
    reg.activate(_AlphaPlugin())
    assert "alpha" in reg.active_plugins

    with caplog.at_level(logging.WARNING):
        reg.activate(_BetaPlugin())
    assert "beta" not in reg.active_plugins
    assert "conflicts with" in caplog.text


def test_conflict_activate_all(caplog: pytest.LogCaptureFixture) -> None:
    """activate_all skips the second conflicting plugin."""
    reg = PluginRegistry()
    reg._discovered["alpha"] = _AlphaPlugin
    reg._discovered["beta"] = _BetaPlugin

    with caplog.at_level(logging.WARNING):
        activated = reg.activate_all(["alpha", "beta"])

    assert len(activated) == 1
    assert "alpha" in reg.active_plugins
    assert "beta" not in reg.active_plugins
