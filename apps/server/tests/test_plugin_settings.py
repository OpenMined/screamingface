"""Tests for plugin settings: typed config, env overrides, system deps, and schema API."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.claude_proxy.plugin import ClaudeProxySettings


# --- Settings resolution ---


def test_settings_defaults() -> None:
    settings = ClaudeProxySettings()
    assert settings.upstream_url == "https://api.anthropic.com"
    assert settings.api_key_env == "ANTHROPIC_API_KEY"


def test_settings_init_override() -> None:
    settings = ClaudeProxySettings(upstream_url="http://custom")
    assert settings.upstream_url == "http://custom"


def test_env_var_wins_over_init(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_CLAUDE_PROXY__UPSTREAM_URL", "http://env")
    settings = ClaudeProxySettings(upstream_url="http://json")
    assert settings.upstream_url == "http://env"


# --- System dependency checks ---


def test_system_dep_check_passes() -> None:
    """Plugin with system_deps=['python3'] should activate without error."""
    from screamingface.core.registry import PluginRegistry

    class GoodPlugin(Plugin):
        name = "good-plugin"
        system_deps = ["python3"]

    registry = PluginRegistry()
    registry._discovered["good-plugin"] = GoodPlugin
    plugin = registry.load_plugin("good-plugin")
    # activate with minimal kwargs — setup() is a no-op on base Plugin
    registry.activate(plugin, app=None, hooks=None, classes=None, routes=None)
    assert "good-plugin" in registry.active_plugins


def test_system_dep_check_fails(caplog: pytest.LogCaptureFixture) -> None:
    """Plugin requiring a nonexistent tool should be skipped with a warning."""
    from screamingface.core.registry import PluginRegistry

    class BadPlugin(Plugin):
        name = "bad-plugin"
        system_deps = ["nonexistent_xyz_tool_12345"]

    registry = PluginRegistry()
    registry._discovered["bad-plugin"] = BadPlugin
    plugin = registry.load_plugin("bad-plugin")
    with caplog.at_level(logging.WARNING):
        registry.activate(plugin, app=None, hooks=None, classes=None, routes=None)
    assert "bad-plugin" not in registry.active_plugins
    assert "nonexistent_xyz_tool_12345" in caplog.text


# --- API endpoints ---


@pytest.fixture
def proxy_settings_app() -> FastAPI:
    config = AppConfig(
        plugins=["claude-proxy"],
        plugin_config={
            "claude-proxy": {
                "upstream_url": "https://api.anthropic.com",
                "api_key_env": "ANTHROPIC_API_KEY",
            }
        },
    )
    return create_app(config)


@pytest.fixture
def settings_client(proxy_settings_app: FastAPI) -> TestClient:
    return TestClient(proxy_settings_app)


def test_plugins_list_endpoint(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins")
    assert resp.status_code == 200
    data = resp.json()
    assert "claude-proxy" in data
    assert data["claude-proxy"]["version"] == "0.1.0"
    assert data["claude-proxy"]["has_settings"] is True


def test_plugin_schema_endpoint(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins/claude-proxy/schema")
    assert resp.status_code == 200
    schema = resp.json()
    assert "properties" in schema
    assert "upstream_url" in schema["properties"]
    assert "api_key_env" in schema["properties"]


def test_plugin_settings_endpoint(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins/claude-proxy/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["upstream_url"] == "https://api.anthropic.com"
    assert data["api_key_env"] == "ANTHROPIC_API_KEY"


def test_plugin_schema_not_found(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins/nonexistent/schema")
    assert resp.status_code == 404


def test_plugin_settings_not_found(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins/nonexistent/settings")
    assert resp.status_code == 404
