"""Profileless Gemini contracts must describe the backend dispatch will use."""

from __future__ import annotations

import pytest

from aigateway.plugins.gemini_provider.discovery import DISCOVERY_SOURCE
from aigateway.plugins.gemini_provider.plugin import GeminiProviderPlugin
from aigateway.routes.chat_credentials import resolved_auth_mode


@pytest.mark.parametrize("environment_name", ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
def test_environment_api_key_selects_api_key_contract_and_public_evidence(
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv(environment_name, "secret-value")
    plugin = GeminiProviderPlugin()

    auth_mode = resolved_auth_mode(None, None, plugin=plugin)
    observations = plugin.chat_parameter_observations(
        model="gemini-cli/gemini-2.5-pro",
        auth_type=auth_mode,
    )
    source = plugin.chat_discovery_source(
        model="gemini-cli/gemini-2.5-pro",
        auth_type=auth_mode,
    )

    assert auth_mode == "api_key"
    assert {observation.source for observation in observations} == {DISCOVERY_SOURCE}
    assert source is not None
    assert source.source == DISCOVERY_SOURCE
