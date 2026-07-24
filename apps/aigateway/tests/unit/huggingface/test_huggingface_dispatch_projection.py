"""Phase 7d (OME-479 §4.6/§6.2): Hugging Face dispatch projection + cache isolation.

FEATURE: Hugging Face P0 observation overlay — the DISPATCH side. Proves the plan's
Phase 7 step 5: the pinned-router origin and request-local credential survive the
fail-closed projection pipeline intact, and a request carrying a projected output
parameter can never take a cached response meant for a different one.

INVARIANT (§6.2): parameter projection COMPOSES with the existing SF-345 hardening —
``prepare_chat_body`` still pins the HF router ``api_base`` and strips the caller's
token, alongside the projected ``temperature``/``max_tokens``.
INVARIANT (§4.6): HF's enabled params land TOP-LEVEL, so any output-affecting param
makes the body cache-ineligible; combined with the always-pinned router base, a real
HF dispatch body is structurally cache-isolated — no shape both dispatches and caches.
"""

from __future__ import annotations

import pytest

from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from aigateway.core.request_cache.keys import CacheBypass, CacheKeyResult, build_cache_key
from aigateway.plugins.huggingface_provider.plugin import HuggingFaceProviderPlugin

_MODEL = "huggingface/openai/gpt-oss-120b:cerebras"
_MESSAGES = [{"role": "user", "content": "hi"}]
_ROUTER_API_BASE = HuggingFaceProviderPlugin().settings.router_api_base


def _dispatch_body(caller_body: dict) -> dict:
    # The exact route pipeline (routes/chat.py), minus profile defaults (empty
    # here): strip provider controls → fail-closed classify/project → prepare.
    plugin = HuggingFaceProviderPlugin()
    stripped = plugin.strip_provider_dispatch_controls(caller_body)
    projected = classify_and_project_chat_parameters(
        stripped,
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
        auth_mode="api_key",
    )
    return plugin.prepare_chat_body(projected)


def _key(normalized_body: dict) -> CacheKeyResult | CacheBypass:
    # routes/chat_dispatch.py keys the POST-prepare_chat_body body (keys.py docstring).
    return build_cache_key(
        account_id="acct-1",
        profile_name="default",
        provider="huggingface",
        normalized_body=normalized_body,
    )


def test_enabled_params_compose_with_pinned_router_and_request_local_token() -> None:
    body = _dispatch_body(
        {"model": _MODEL, "messages": _MESSAGES, "temperature": 0.5, "max_tokens": 128}
    )
    # SF-345 hardening intact ALONGSIDE the projected params (Phase 7 step 5):
    assert body["api_base"] == _ROUTER_API_BASE  # pinned-router origin
    assert "api_key" not in body  # request-local credential is never forwarded here
    # the projected standard fields stay top-level, ready for the installed transform.
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 128


def test_caller_supplied_api_key_is_rejected_not_forwarded() -> None:
    # fail-closed defense distinct from an ordinary unruled param: a caller cannot
    # smuggle an api_key as a "parameter" — it is unknown to the rules and rejected
    # before any credential work, so it never reaches prepare_chat_body's strip.
    plugin = HuggingFaceProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "api_key": "hf_nope"},
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    assert "api_key" in exc.value.rejected


def test_real_dispatch_body_bypasses_cache_never_shares_a_key() -> None:
    # §4.6 end-to-end (FAITHFUL): the REAL post-prepare HF body — pinned router base
    # PLUS a projected temperature — is cache-ineligible. Two temperatures BOTH
    # bypass, so a request can never be served a response produced with a different
    # one. This is the honest HF guarantee: a dispatchable body never caches.
    half = _key(_dispatch_body({"model": _MODEL, "messages": _MESSAGES, "temperature": 0.5}))
    assert isinstance(half, CacheBypass)
    assert half.reason == "unsupported_fields"
    assert isinstance(
        _key(_dispatch_body({"model": _MODEL, "messages": _MESSAGES, "temperature": 0.9})),
        CacheBypass,
    )


def test_core_key_rule_isolates_a_projected_output_param() -> None:
    # CORE-RULE characterization: a projected output param INDEPENDENTLY forces
    # bypass (not only the pinned api_base). Keyed without transport fields to
    # isolate temperature as the sole cause.
    result = _key({"model": _MODEL, "messages": _MESSAGES, "temperature": 0.5})
    assert isinstance(result, CacheBypass)
    assert result.reason == "unsupported_fields"


def test_core_key_rule_keys_a_bare_prompt() -> None:
    # CORE-RULE contrast: the SAME model+prompt with NO params is eligible — proving
    # the bypass above is param-driven discrimination, not a blanket HF bypass.
    result = _key({"model": _MODEL, "messages": _MESSAGES})
    assert isinstance(result, CacheKeyResult)
