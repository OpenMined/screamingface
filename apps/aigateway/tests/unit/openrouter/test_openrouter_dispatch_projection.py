"""Phase 6d (OME-479 §4.6/§6.1): OpenRouter dispatch-side projection + cache isolation.

FEATURE: OpenRouter P0 observation overlay — the DISPATCH side. Proves the fail-
closed classifier + provider projection produce the exact serialized body
OpenRouter dispatch sends: the P0-promoted provider_params.top_k lands at its
native extra_body target, an unruled field is rejected BEFORE any credential is
read, and a request carrying an output-affecting parameter can never take a cached
response meant for a different one (§4.6 cache isolation).

INVARIANT: parameter projection COMPOSES with the existing OME-428 hardening — the
pinned official api_base and gateway-owned attribution headers survive intact
alongside the projected params, and a caller-supplied api_key never dispatches.
INVARIANT (§4.6): a body carrying a projected optional parameter is not cacheable,
so a differently-parameterized request can never share its key.
"""

from __future__ import annotations

import pytest

from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from aigateway.core.request_cache.keys import CacheBypass, CacheKeyResult, build_cache_key
from aigateway.plugins.openrouter_provider.plugin import (
    OFFICIAL_API_BASE,
    OpenRouterProviderPlugin,
)

_MODEL = "openrouter/google/gemini-2.0-flash-001"
_MESSAGES = [{"role": "user", "content": "hi"}]


def _dispatch_body(caller_body: dict) -> dict:
    # The exact route pipeline (routes/chat.py), minus profile defaults (empty
    # here): strip provider controls → fail-closed classify/project → prepare.
    plugin = OpenRouterProviderPlugin()
    stripped = plugin.strip_provider_dispatch_controls(caller_body)
    projected = classify_and_project_chat_parameters(
        stripped,
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
        auth_mode="api_key",
    )
    return plugin.prepare_chat_body(projected)


def test_native_top_k_promotes_to_extra_body_target() -> None:
    body = _dispatch_body(
        {
            "model": _MODEL,
            "messages": _MESSAGES,
            "temperature": 0.5,
            "provider_params": {"top_k": 40},
        }
    )
    # the P0 promotion: provider_params.top_k → extra_body.top_k (the installed
    # litellm transform carries extra_body onto the OpenRouter wire); the standard
    # temperature stays a top-level field.
    assert body["extra_body"] == {"top_k": 40}
    assert body["temperature"] == 0.5
    # the wrapper is fully consumed — a raw provider_params never dispatches, and
    # the native name never leaks to the bare top level.
    assert "provider_params" not in body
    assert "top_k" not in body


def test_projection_composes_with_existing_hardening() -> None:
    body = _dispatch_body(
        {"model": _MODEL, "messages": _MESSAGES, "provider_params": {"top_k": 40}}
    )
    # OME-428 hardening intact alongside the projected param:
    assert body["api_base"] == OFFICIAL_API_BASE
    assert body["extra_headers"]["X-Title"] == "ScreamingFace"
    assert "api_key" not in body
    assert body["extra_body"] == {"top_k": 40}


def test_unruled_parameter_is_rejected_fail_closed() -> None:
    plugin = OpenRouterProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "top_p": 0.9},
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    # top_p is observed-but-unruled: VISIBLE in the detail contract, REJECTED at
    # dispatch — the two projections of one source agree.
    assert exc.value.rejected == {"top_p": "unknown"}


def test_caller_supplied_api_key_is_rejected_not_forwarded() -> None:
    # fail-closed defense: a caller cannot smuggle an api_key as a "parameter"; it
    # is unknown to the rule set and rejected before any credential work.
    plugin = OpenRouterProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "api_key": "sk-nope"},
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    assert "api_key" in exc.value.rejected


def test_top_k_bearing_body_bypasses_cache_never_shares_a_key() -> None:
    # §4.6 isolation: a normalized body carrying the projected top_k is NOT
    # cacheable, so it can never be served a response produced with a different
    # top_k. Two different top_k values BOTH bypass — there is no shared key.
    def key_for(top_k: int) -> CacheKeyResult | CacheBypass:
        return build_cache_key(
            account_id="acct-1",
            profile_name="default",
            provider="openrouter",
            normalized_body={
                "model": _MODEL,
                "messages": _MESSAGES,
                "extra_body": {"top_k": top_k},
            },
        )

    forty = key_for(40)
    assert isinstance(forty, CacheBypass)
    assert forty.reason == "unsupported_fields"
    assert isinstance(key_for(80), CacheBypass)


def test_bare_prompt_without_params_remains_cacheable() -> None:
    # the isolation is SPECIFIC to output-affecting params: the same prompt with NO
    # parameters is cacheable, proving it is the projected top_k that forces bypass.
    result = build_cache_key(
        account_id="acct-1",
        profile_name="default",
        provider="openrouter",
        normalized_body={"model": _MODEL, "messages": _MESSAGES},
    )
    assert isinstance(result, CacheKeyResult)
