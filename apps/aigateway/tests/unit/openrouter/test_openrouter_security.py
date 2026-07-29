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
                    "X-Trace-Id": "trace-123",
                }
            },
        )
    assert resp.status_code == 200, resp.text
    headers = captured["extra_headers"]
    assert headers["HTTP-Referer"] == "https://screamingface.ai"
    assert headers["X-OpenRouter-Title"] == "ScreamingFace"
    assert headers["X-Title"] == "ScreamingFace"
    assert "X-Trace-Id" not in headers
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
    """D7 local BYOK: schema-backed sampling fields survive to dispatch.

    Scope narrowed by OME-646: the four native routing controls this also covered are
    no longer forwarded — they are refused, and are asserted as such below.
    """
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"temperature": 0.25, "max_tokens": 64})
    assert resp.status_code == 200, resp.text
    assert captured["temperature"] == 0.25
    assert captured["max_tokens"] == 64


# --- provider-native routing controls are OUT of scope (OME-646) ----------------
#
# WHY these four are refused rather than forwarded: each was enabled by a rule carrying
# NO validation schema, so the gateway authorized a path and forwarded arbitrary nested
# JSON verbatim. An enabled ordinary parameter must declare a gateway-owned validation
# schema (§Definition of done), and `route`/`models`/`provider.allow_fallbacks` are
# fallback and routing controls that the task's excluded scope names outright. Either
# classification forbids the rule as written, so the rules were removed.
#
# INVARIANT: this closes an asymmetry with the test above it —
# test_nested_fallbacks_and_model_list_never_reach_litellm strips LiteLLM's own
# `fallbacks`/`model_list` because a caller could redirect dispatch with them, while
# `route: "fallback"` + `models: [...]` is OpenRouter's server-side spelling of the same
# capability. The gateway blocked one and forwarded the other.
_NATIVE_ROUTING_CONTROLS = {
    "provider": {"order": ["anthropic"], "allow_fallbacks": False},
    "plugins": [{"id": "web"}],
    "route": "fallback",
    "models": ["openrouter/anthropic/claude-opus-4.8"],
}


@pytest.mark.parametrize(("path", "value"), sorted(_NATIVE_ROUTING_CONTROLS.items()))
def test_native_routing_controls_are_refused(
    path, value, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    resp = _post_chat(authenticated_client, {path: value})
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "unsupported_parameters"
    # Fail closed and SAY SO: the field is named, never silently dropped.
    assert detail["rejected"] == {path: "unknown"}


def test_the_refusal_of_a_native_routing_control_precedes_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # Ordering proof without instrumentation: a tripwire on the provider's body
    # preparation fires if classification let the request through to the provider.
    _create_connection(authenticated_client)

    def _tripwire(_self, _body):
        raise AssertionError("prepare_chat_body ran on a refused routing control")

    target = "aigateway.plugins.openrouter_provider.plugin.OpenRouterProviderPlugin"
    with patch(f"{target}.prepare_chat_body", _tripwire):
        resp = _post_chat(authenticated_client, {"route": "fallback"})

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unsupported_parameters"


def test_caller_api_key_never_reaches_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"api_key": "sk-evil-caller"})
    assert resp.status_code == 200, resp.text
    assert captured["api_key"] == _KEY
