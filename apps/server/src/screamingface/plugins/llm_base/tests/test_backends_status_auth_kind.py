"""Tests for the auth_kind field on the /backends/status payload.

Plugins that declare ``gateway_provider`` get auth_kind="browser"; all
others (CLI-spawn flow) get auth_kind="cli".
"""

from __future__ import annotations

from screamingface.plugins.llm_base.routes import _classify_auth_kind


class _CliPlugin:
    name = "provider-backend-api"
    backend_call_paths = ["/provider"]


class _BrowserPlugin:
    name = "aigw-provider-backend"
    backend_call_paths = ["/provider"]
    gateway_provider = "test-provider"


class _AlternateBrowserPlugin:
    name = "aigw-alternate-backend"
    backend_call_paths = ["/alternate"]
    gateway_provider = "alternate-provider"


def test_auth_kind_browser_when_plugin_has_gateway_provider() -> None:
    assert _classify_auth_kind(_BrowserPlugin) == "browser"


def test_auth_kind_browser_for_other_gateway_backed_plugin() -> None:
    assert _classify_auth_kind(_AlternateBrowserPlugin) == "browser"


def test_auth_kind_cli_when_plugin_lacks_gateway_provider() -> None:
    assert _classify_auth_kind(_CliPlugin) == "cli"


def test_auth_kind_cli_when_gateway_provider_is_none() -> None:
    class _P:
        gateway_provider = None

    assert _classify_auth_kind(_P) == "cli"
