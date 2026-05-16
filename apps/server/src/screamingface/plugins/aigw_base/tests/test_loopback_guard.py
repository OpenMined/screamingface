from __future__ import annotations

from fastapi import FastAPI

from screamingface.core.config import AppConfig, ServerConfig
from screamingface.plugins.aigw_claude_backend.plugin import AigwClaudeBackendPlugin


def _app_with_host(host: str) -> FastAPI:
    app = FastAPI()
    app.state.config = AppConfig(server=ServerConfig(host=host))
    return app


def test_gateway_backed_plugin_allows_loopback_host() -> None:
    plugin = AigwClaudeBackendPlugin()
    plugin._assert_loopback_server_bind(FastAPI())
    plugin._assert_loopback_server_bind(_app_with_host(""))
    plugin._assert_loopback_server_bind(_app_with_host("127.0.0.1"))
    plugin._assert_loopback_server_bind(_app_with_host("localhost"))
    plugin._assert_loopback_server_bind(_app_with_host("::1"))


def test_gateway_backed_plugin_blocks_lan_host_without_override() -> None:
    plugin = AigwClaudeBackendPlugin()

    try:
        plugin._assert_loopback_server_bind(_app_with_host("0.0.0.0"))
    except RuntimeError as exc:
        assert "non-loopback" in str(exc)
    else:
        raise AssertionError("expected non-loopback host to be rejected")


def test_gateway_backed_plugin_allows_lan_host_with_override(monkeypatch) -> None:
    monkeypatch.setenv("SF_AIGW_ALLOW_LAN", "1")
    plugin = AigwClaudeBackendPlugin()
    plugin._assert_loopback_server_bind(_app_with_host("0.0.0.0"))
