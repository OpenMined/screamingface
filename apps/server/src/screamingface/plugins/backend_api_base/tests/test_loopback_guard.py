from __future__ import annotations

from fastapi import FastAPI

from screamingface.core.config import AppConfig, ServerConfig
from screamingface.plugins.claude_backend_api.plugin import ClaudeBackendApiPlugin


def _app_with_host(host: str) -> FastAPI:
    app = FastAPI()
    app.state.config = AppConfig(server=ServerConfig(host=host))
    return app


def test_direct_backend_plugin_allows_loopback_host() -> None:
    plugin = ClaudeBackendApiPlugin()
    plugin._assert_loopback_server_bind(FastAPI())
    plugin._assert_loopback_server_bind(_app_with_host("127.0.0.1"))
    plugin._assert_loopback_server_bind(_app_with_host("localhost"))
    plugin._assert_loopback_server_bind(_app_with_host("::1"))


def test_direct_backend_plugin_blocks_lan_host_without_override() -> None:
    plugin = ClaudeBackendApiPlugin()

    try:
        plugin._assert_loopback_server_bind(_app_with_host("0.0.0.0"))
    except RuntimeError as exc:
        assert "non-loopback" in str(exc)
        assert "SF_SERVER_ALLOW_LAN=1" in str(exc)
    else:
        raise AssertionError("expected non-loopback host to be rejected")


def test_direct_backend_plugin_blocks_empty_host_without_override() -> None:
    plugin = ClaudeBackendApiPlugin()

    try:
        plugin._assert_loopback_server_bind(_app_with_host(""))
    except RuntimeError as exc:
        assert "non-loopback" in str(exc)
    else:
        raise AssertionError("expected empty host to be rejected")


def test_direct_backend_plugin_still_blocks_backend_only_override(monkeypatch) -> None:
    monkeypatch.setenv("SF_BACKEND_API_ALLOW_LAN", "1")
    plugin = ClaudeBackendApiPlugin()

    try:
        plugin._assert_loopback_server_bind(_app_with_host("0.0.0.0"))
    except RuntimeError as exc:
        assert "SF_SERVER_ALLOW_LAN=1" in str(exc)
    else:
        raise AssertionError("expected shared server override to be required")


def test_direct_backend_plugin_allows_lan_host_with_shared_override(monkeypatch) -> None:
    monkeypatch.setenv("SF_SERVER_ALLOW_LAN", "1")
    plugin = ClaudeBackendApiPlugin()
    plugin._assert_loopback_server_bind(_app_with_host("0.0.0.0"))
