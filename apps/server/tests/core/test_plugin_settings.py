"""Tests for plugin settings: typed config, env overrides, system deps, and schema API."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugin import Plugin
from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings

# --- Settings resolution ---


def test_settings_defaults() -> None:
    settings = ClaudeFrontendSettings()
    assert settings.upstream_url == "https://api.anthropic.com"
    assert settings.listen_port == 9101
    assert settings.active_spec is None


def test_settings_init_override() -> None:
    settings = ClaudeFrontendSettings(upstream_url="http://custom")
    assert settings.upstream_url == "http://custom"


def test_env_var_wins_over_init(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_CLAUDE_FRONTEND__UPSTREAM_URL", "http://env")
    settings = ClaudeFrontendSettings(upstream_url="http://json")
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


async def _noop_serve():
    pass


def _mock_frontend_server():
    """Context manager that prevents claude-frontend from starting a real server."""
    mock_server = MagicMock()
    mock_server.should_exit = False
    mock_server.serve = _noop_serve
    return (
        patch("shutil.which", return_value="/usr/bin/claude"),
        patch("screamingface.plugins.frontend_base.plugin_base.uvicorn.Config"),
        patch(
            "screamingface.plugins.frontend_base.plugin_base.uvicorn.Server",
            return_value=mock_server,
        ),
        patch(
            "screamingface.plugins.frontend_base.plugin_base._wait_for_port",
            return_value=True,
        ),
    )


@pytest.fixture
def proxy_settings_app() -> FastAPI:
    config = AppConfig(
        plugins=["claude-frontend"],
        plugin_config={
            "claude-frontend": {
                "upstream_url": "https://api.anthropic.com",
                "listen_port": 18081,
            }
        },
    )
    p1, p2, p3, p4 = _mock_frontend_server()
    with p1, p2, p3, p4:
        return create_app(config)


@pytest.fixture
def settings_client(proxy_settings_app: FastAPI) -> TestClient:
    return TestClient(proxy_settings_app)


def test_plugins_list_endpoint(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins")
    assert resp.status_code == 200
    data = resp.json()
    assert "claude-frontend" in data
    assert data["claude-frontend"]["version"] == "0.1.0"
    assert data["claude-frontend"]["has_settings"] is True


def test_plugin_schema_endpoint(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins/claude-frontend/schema")
    assert resp.status_code == 200
    schema = resp.json()
    assert "properties" in schema
    assert "upstream_url" in schema["properties"]
    assert "listen_port" in schema["properties"]
    assert "active_spec" in schema["properties"]


def test_plugin_settings_endpoint(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins/claude-frontend/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["upstream_url"] == "https://api.anthropic.com"
    # Settings endpoint re-reads sf.json, so the value reflects the
    # config file (9101) rather than the fixture's in-memory override.
    assert isinstance(data["listen_port"], int)


def test_plugin_schema_not_found(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins/nonexistent/schema")
    assert resp.status_code == 404


def test_plugin_settings_not_found(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins/nonexistent/settings")
    assert resp.status_code == 404
