"""Tests for the auth_kind field on the /backends/status payload.

Plugins that declare ``gateway_provider`` get auth_kind="browser"; all
others (CLI-spawn flow) get auth_kind="cli".
"""

from __future__ import annotations

from screamingface.plugins.llm_base.routes import _classify_auth_kind


class _CliPlugin:
    name = "claude-backend-api"
    backend_call_paths = ["/claude"]


class _BrowserPlugin:
    name = "aigw-claude-backend"
    backend_call_paths = ["/claude"]
    gateway_provider = "anthropic"


class _CodexBrowserPlugin:
    name = "aigw-codex-backend"
    backend_call_paths = ["/codex"]
    gateway_provider = "codex"


def test_auth_kind_browser_when_plugin_has_gateway_provider() -> None:
    assert _classify_auth_kind(_BrowserPlugin) == "browser"


def test_auth_kind_browser_for_gateway_backed_codex() -> None:
    assert _classify_auth_kind(_CodexBrowserPlugin) == "browser"


def test_auth_kind_cli_when_plugin_lacks_gateway_provider() -> None:
    assert _classify_auth_kind(_CliPlugin) == "cli"


def test_auth_kind_cli_when_gateway_provider_is_none() -> None:
    class _P:
        gateway_provider = None

    assert _classify_auth_kind(_P) == "cli"
