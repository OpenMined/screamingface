"""Poisoned LiteLLM global/env fallback contracts (OME-428 Phase 3).

LiteLLM 1.87.0 resolves OpenRouter credentials request-locally FIRST
(main.py: request api_key beats litellm.api_key -> litellm.openrouter_key ->
env OPENROUTER_API_KEY -> OR_API_KEY; request api_base beats litellm.api_base
-> env OPENROUTER_API_BASE; caller headers beat OR_SITE_URL/OR_APP_NAME
attribution defaults). These tests poison EVERY fallback and prove the
gateway always supplies request-local values at the acompletion boundary, so
none of the poisoned globals can ever be consulted for a BYOK dispatch."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import litellm
import pytest

from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_OFFICIAL_API_BASE = "https://openrouter.ai/api/v1"
_KEY = "sk-or-v1-byok"
_POISON = "sk-or-poisoned"


@pytest.fixture()
def enabled_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN, "settings", OpenRouterPluginSettings(enabled=True)
    )


@pytest.fixture()
def poisoned_litellm_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(litellm, "api_key", f"{_POISON}-litellm-api-key")
    monkeypatch.setattr(litellm, "openrouter_key", f"{_POISON}-litellm-openrouter-key")
    monkeypatch.setattr(litellm, "api_base", "https://poisoned.example/litellm")
    monkeypatch.setenv("OPENROUTER_API_KEY", f"{_POISON}-env-openrouter")
    monkeypatch.setenv("OR_API_KEY", f"{_POISON}-env-or")
    monkeypatch.setenv("OPENROUTER_API_BASE", "https://poisoned.example/env")
    monkeypatch.setenv("OR_SITE_URL", "https://poisoned.example/site")
    monkeypatch.setenv("OR_APP_NAME", "poisoned-app")


def test_request_local_credentials_beat_poisoned_globals(
    enabled_openrouter, poisoned_litellm_globals, credential_blobs, authenticated_client
) -> None:
    create = authenticated_client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": "work-openrouter", "api_key": _KEY},
    )
    assert create.status_code == 201, create.text

    captured: dict = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model_dump=lambda: {"id": "or-1", "choices": [{"message": {"content": "ok"}}]}
        )

    with patch("litellm.acompletion", fake_acompletion):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "openrouter/anthropic/claude-fable-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200, resp.text
    # Request-local values are present at the acompletion boundary, so none
    # of LiteLLM's global/env fallbacks can be consulted (verified against
    # litellm 1.87.0 main.py precedence).
    assert captured["api_key"] == _KEY
    assert captured["api_base"] == _OFFICIAL_API_BASE
    headers = captured["extra_headers"]
    assert headers["HTTP-Referer"] == "https://screamingface.ai"
    assert headers["X-OpenRouter-Title"] == "ScreamingFace"
    assert headers["X-Title"] == "ScreamingFace"
    serializable = {key: value for key, value in captured.items() if key != "client"}
    assert "poisoned" not in json.dumps(serializable)
