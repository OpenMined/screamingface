"""OpenRouter dispatch security wire contracts (OME-428 Phase 3, plan D6/D7).

These run the REAL OpenRouterProviderPlugin.chat_completion and capture the
kwargs handed to ``litellm.acompletion`` — the last gateway-controlled point
before the wire — proving pinned api_base, trusted attribution, control
stripping, and legitimate-field passthrough at dispatch."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_OFFICIAL_API_BASE = "https://openrouter.ai/api/v1"
_KEY = "sk-or-v1-test"


@pytest.fixture()
def enabled_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN, "settings", OpenRouterPluginSettings(enabled=True)
    )


def _create_connection(client) -> None:
    resp = client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": "work-openrouter", "api_key": _KEY},
    )
    assert resp.status_code == 201, resp.text


def _fake_acompletion(captured: dict):
    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model_dump=lambda: {"id": "or-1", "choices": [{"message": {"content": "ok"}}]}
        )

    return fake_acompletion


def _post_chat(client, body: dict):
    payload = {
        "model": "openrouter/anthropic/claude-fable-5",
        "messages": [{"role": "user", "content": "hi"}],
        **body,
    }
    return client.post("/v1/chat/completions", json=payload)


def test_dispatch_pins_official_api_base_over_caller_values(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(
            authenticated_client,
            {"api_base": "https://evil.example/api", "base_url": "https://evil.example"},
        )
    assert resp.status_code == 200, resp.text
    assert captured["api_base"] == _OFFICIAL_API_BASE
    assert "base_url" not in captured


def test_trusted_attribution_overrides_caller_headers(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    """Caller attribution/auth headers are dropped; the gateway's trusted
    identity is injected (D7). LiteLLM lets caller headers override its
    OR_SITE_URL/OR_APP_NAME defaults, so the gateway must own these keys."""
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(
            authenticated_client,
            {
                "extra_headers": {
                    "HTTP-Referer": "https://evil.example",
                    "Referer": "https://evil.example",
                    "X-OpenRouter-Title": "evil",
                    "x-title": "evil",
                    "Authorization": "Bearer sk-evil",
                    "X-Api-Key": "sk-evil",
                    "X-Trace-Id": "trace-123",  # ordinary caller header survives
                }
            },
        )
    assert resp.status_code == 200, resp.text
    headers = captured["extra_headers"]
    assert headers["HTTP-Referer"] == "https://screamingface.ai"
    assert headers["X-OpenRouter-Title"] == "ScreamingFace"
    assert headers["X-Title"] == "ScreamingFace"
    assert headers["X-Trace-Id"] == "trace-123"
    assert "evil" not in json.dumps(headers).lower()
    assert not any(key.lower() in {"authorization", "x-api-key"} for key in headers)


def test_nested_fallbacks_and_model_list_never_reach_litellm(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    """Regression for the nested-redirect exfiltration path: fallbacks /
    model_list would make LiteLLM re-dispatch with attacker-controlled
    api_base entries. They must be gone by the acompletion call."""
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(
            authenticated_client,
            {
                "fallbacks": [
                    {
                        "model": "openrouter/anthropic/claude-fable-5",
                        "api_base": "https://evil.example",
                    }
                ],
                "model_list": [
                    {
                        "model_name": "openrouter/anthropic/claude-fable-5",
                        "litellm_params": {"api_base": "https://evil.example"},
                    }
                ],
                "context_window_fallbacks": [{"model": "x"}],
            },
        )
    assert resp.status_code == 200, resp.text
    assert "fallbacks" not in captured
    assert "model_list" not in captured
    assert "context_window_fallbacks" not in captured
    assert "evil.example" not in json.dumps({k: v for k, v in captured.items() if k != "api_key"})
    assert captured["api_base"] == _OFFICIAL_API_BASE


def test_ordinary_openrouter_fields_pass_through(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    """D7 local BYOK: legitimate OpenRouter extensions survive to dispatch."""
    _create_connection(authenticated_client)
    captured: dict = {}
    provider_prefs = {"order": ["anthropic"], "allow_fallbacks": False}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(
            authenticated_client,
            {
                "provider": provider_prefs,
                "plugins": [{"id": "web"}],
                "route": "fallback",
                "models": ["openrouter/anthropic/claude-opus-4.8"],
                "temperature": 0.25,
                "max_tokens": 64,
            },
        )
    assert resp.status_code == 200, resp.text
    assert captured["provider"] == provider_prefs
    assert captured["plugins"] == [{"id": "web"}]
    assert captured["route"] == "fallback"
    assert captured["models"] == ["openrouter/anthropic/claude-opus-4.8"]
    assert captured["temperature"] == 0.25
    assert captured["max_tokens"] == 64


def test_caller_api_key_never_reaches_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"api_key": "sk-evil-caller"})
    assert resp.status_code == 200, resp.text
    assert captured["api_key"] == _KEY
