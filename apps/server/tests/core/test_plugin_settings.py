"""Tests for plugin settings: typed config, env overrides, system deps, and schema API."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface import __version__ as sf_version
from screamingface.core.admin_router import register_admin_routes
from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)
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
    assert data["claude-frontend"]["version"] == sf_version
    assert data["claude-frontend"]["has_settings"] is True


def test_backend_aliases_endpoint_uses_active_profile_capable_plugins() -> None:
    class AliasSettings(PluginSettings):
        profiles: dict[str, str]

    class ProfileBackend(Plugin):
        name = "profile-backend"
        backend_call_paths = ["/hf", "/huggingface"]
        supports_profile_aliases = True

    class PlainBackend(Plugin):
        name = "plain-backend"
        backend_call_paths = ["/plain"]

    profile_backend = ProfileBackend()
    profile_backend.settings = AliasSettings(profiles={"oss20b": "", "fast": ""})
    plain_backend = PlainBackend()
    plain_backend.settings = AliasSettings(profiles={"hidden": ""})

    app = FastAPI()
    app.state.plugins = SimpleNamespace(
        active_plugins={
            profile_backend.name: profile_backend,
            plain_backend.name: plain_backend,
        }
    )
    register_admin_routes(app)

    resp = TestClient(app).get("/plugins/backend-aliases")

    assert resp.status_code == 200
    assert resp.json() == {
        "aliases": ["/hf/oss20b", "/hf/fast", "/huggingface/oss20b", "/huggingface/fast"],
        "backends": [
            {
                "plugin": "profile-backend",
                "paths": ["/hf", "/huggingface"],
                "profiles": ["oss20b", "fast"],
            }
        ],
    }


def test_plugin_schema_endpoint(settings_client: TestClient) -> None:
    resp = settings_client.get("/plugins/claude-frontend/schema")
    assert resp.status_code == 200
    schema = resp.json()
    assert "properties" in schema
    assert "upstream_url" in schema["properties"]
    assert "listen_port" in schema["properties"]
    assert "active_spec" in schema["properties"]


def test_real_aigw_plugin_schema_lists_gateway_profiles() -> None:
    gateway_requests: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        gateway_requests.append(str(req.url))
        if req.url.path.endswith("/v1/auth/anthropic/profiles"):
            return httpx.Response(200, json={"profiles": [{"name": "default"}]})
        if req.url.path.endswith("/v1/oauth/connections"):
            return httpx.Response(
                200,
                json={"connections": [{"label": "work-anthropic", "status": "active"}]},
            )
        if req.url.path.endswith("/v1/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "claude-opus-4-8", "object": "model", "owned_by": "anthropic"},
                        # A foreign-provider entry must be filtered out.
                        {"id": "gpt-5.4-mini", "object": "model", "owned_by": "codex"},
                    ]
                },
            )
        raise AssertionError(f"unexpected gateway request: {req.url}")

    plugin = AigwClaudeBackendPlugin()
    plugin.settings = AigwClaudeBackendSettings()
    plugin._http_transport = httpx.MockTransport(handler)  # type: ignore[attr-defined]
    app = FastAPI()
    app.state.config = SimpleNamespace(
        plugin_config={"aigw-base": {"mode": "local_managed", "gateway_url": "http://gateway"}}
    )
    app.state.plugins = SimpleNamespace(active_plugins={plugin.name: plugin})
    plugin._app = app  # type: ignore[attr-defined]
    register_admin_routes(app)
    client = TestClient(app)

    resp = client.get(f"/plugins/{plugin.name}/schema")

    assert resp.status_code == 200
    props = resp.json()["properties"]
    assert props["auth_profile"]["enum"] == ["default", "work-anthropic"]
    # SF-284: model dropdown derived from /v1/models, filtered to this provider
    # and prefixed to the SF `<provider>/<model>` form.
    assert props["default_model"]["examples"] == ["anthropic/claude-opus-4-8"]
    assert gateway_requests == [
        "http://gateway/v1/auth/anthropic/profiles",
        "http://gateway/v1/oauth/connections?provider=anthropic&status=active",
        "http://gateway/v1/models",
    ]


def test_plugin_schema_is_public() -> None:
    class DummySettings(PluginSettings):
        value: str = "ok"

    class PlainPlugin(Plugin):
        name = "plain-plugin"
        settings_class = DummySettings

    plugin = PlainPlugin()
    app = FastAPI()
    app.state.plugins = SimpleNamespace(active_plugins={plugin.name: plugin})
    register_admin_routes(app)

    resp = TestClient(app).get(f"/plugins/{plugin.name}/schema")

    assert resp.status_code == 200
    assert "value" in resp.json()["properties"]


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
