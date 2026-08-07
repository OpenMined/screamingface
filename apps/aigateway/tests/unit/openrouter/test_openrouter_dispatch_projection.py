"""Phase 6d (OME-479 §4.6/§6.1): OpenRouter dispatch-side projection.

FEATURE: OpenRouter P0 observation overlay — the DISPATCH side. Proves the fail-
closed classifier + provider projection produce the exact serialized body
OpenRouter dispatch sends: the P0-promoted provider_params.top_k lands at its
native extra_body target, an unruled field is rejected BEFORE any credential is
read, and a request carrying an output-affecting parameter can never take a cached
response shape expected by the provider.

INVARIANT: parameter projection COMPOSES with the existing OME-428 hardening — the
pinned official api_base and gateway-owned attribution headers survive intact
alongside the projected params, and a caller-supplied api_key never dispatches.
"""

from __future__ import annotations

import litellm
import pytest

from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
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


def test_stop_reaches_dispatch_and_installed_transform() -> None:
    # OME-582 (§9): the enabled stop rule projects the caller field onto the dispatch
    # body, and the INSTALLED litellm OpenRouter path forwards it as the OpenAI-native
    # `stop` — pinned against the installed library, not assumed.
    body = _dispatch_body({"model": _MODEL, "messages": _MESSAGES, "stop": ["\n\n", "END"]})
    assert body["stop"] == ["\n\n", "END"]
    optional = litellm.utils.get_optional_params(
        model="google/gemini-2.0-flash-001",
        custom_llm_provider="openrouter",
        stop=["\n\n", "END"],
    )
    assert optional["stop"] == ["\n\n", "END"]


def test_unruled_parameter_is_rejected_fail_closed() -> None:
    # An observed-but-unruled field is VISIBLE in the detail contract and REJECTED
    # at dispatch — the two projections of one source agree.
    #
    # AIDEV-NOTE: `top_p` used to supply this scenario for free, being the one
    # OpenRouter path that was observed with no rule. It was promoted (OME-479
    # closure Unit 2), so the scenario is now CONSTRUCTED: the real observation set
    # is left untouched and the rule is withheld. Same field, same assertion, and
    # the property is now proven deliberately rather than borrowed from a gap —
    # withholding only the rule is what isolates it as the sole authorizing input.
    plugin = OpenRouterProviderPlugin()
    observed = {o.request_path for o in plugin.chat_parameter_observations(model=_MODEL)}
    assert "top_p" in observed, "the evidence half of the scenario must be real"
    unruled = tuple(
        rule
        for rule in plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key")
        if rule.request_path != "top_p"
    )
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "top_p": 0.9},
            rules=unruled,
            auth_mode="api_key",
        )
    assert exc.value.rejected == {"top_p": "unknown"}


def test_promoted_top_p_projects_to_dispatch() -> None:
    # The other side of the same coin (OME-479 closure Unit 2): WITH its rule, the
    # very same field is accepted and lands at its own top-level target.
    body = _dispatch_body({"model": _MODEL, "messages": _MESSAGES, "top_p": 0.9})
    assert body["top_p"] == 0.9


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
