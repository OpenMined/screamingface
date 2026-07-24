"""Anthropic chat-parameter rules (OME-479 §6.1/§6.3) — proven set only.

INVARIANT (§9): every rule here is backed by a test proving the caller param
reaches the Anthropic dispatch body — the standard fields through the INSTALLED
litellm ``AnthropicConfig`` transform (``test_anthropic_parameter_projection``),
so enabling a field is earned, not speculative.

Auth-mode split (§6.3 — Anthropic offers BOTH api-key and OAuth):

- ``reasoning_effort``, ``temperature``, ``max_tokens``, ``top_p`` — standard
  fields whose forwarding is auth-agnostic (the OAuth Claude-Code attribution
  block only rewrites messages/system; the SAME transform then runs), so they are
  enabled under BOTH modes and survive the conservative summary intersection.
- ``provider_params.top_k`` → native top-level ``top_k`` — enabled for API KEY
  ONLY. The direct api-key path is transform-verifiable here; the OAuth Claude-Code
  SUBSCRIPTION path's native-param forwarding is uncaptured in v1 and §6.3 forbids
  credentialed discovery, so OAuth "cannot prove it". It therefore surfaces ENABLED
  in the api-key detailed contract but is DROPPED from the inline summary
  intersection. Promoting it for OAuth later needs only a captured-body proof.

# AIDEV-NOTE: the caller-facing wrapper ``provider_params.top_k`` matches OpenRouter
# for client consistency; only the projection TARGET is provider-specific (top-level
# top_k here vs extra_body.top_k for OpenRouter). ``stop`` stays observed-but-unruled.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import ParameterProjectionRule, ParameterSchema
from aigateway.core.profile_models import AuthType
from aigateway.core.standard_parameters import (
    MAX_TOKENS_SCHEMA,
    REASONING_EFFORT_SCHEMA,
    TOP_K_SCHEMA,
    TOP_P_SCHEMA,
    direct_rule,
    provider_native_rule,
)

# reasoning_effort/temperature/max_tokens/top_p are model behavior, not auth-specific
# features, so they are enabled under both modes (surviving the summary intersection).
_AUTH: tuple[AuthType, ...] = ("api_key", "oauth")
# top_k: proven through the DIRECT api-key transform only (OAuth subscription path
# uncaptured in v1) — so it is authorized under api_key alone.
_API_KEY_ONLY: tuple[AuthType, ...] = ("api_key",)
_REVISION = "anthropic-2026-07"

# WHY: Anthropic's Messages API accepts temperature in [0, 1] (NOT the shared
# OpenAI-compatible [0, 2]), and the installed litellm AnthropicConfig forwards the
# value with no clamp — so the gateway must enforce the real bound here or forward a
# value the provider 400s. Provider-local by design: standard_parameters forbids
# provider-specific ranges (its "no provider names appear here" invariant).
ANTHROPIC_TEMPERATURE_SCHEMA = ParameterSchema(type="number", minimum=0, maximum=1)

_RULES: tuple[ParameterProjectionRule, ...] = (
    # direct: stays top-level as reasoning_effort (prepare_chat_body drops the
    # value "none" AFTER classification); schema accepts "none".
    direct_rule(
        "reasoning_effort",
        auth_modes=_AUTH,
        schema=REASONING_EFFORT_SCHEMA,
        projection_revision=_REVISION,
    ),
    # direct: standard sampling param a client sends bare — proven to reach the
    # Anthropic dispatch body (cache-bypass) by
    # test_chat_request_cache.py::test_unsupported_field_bypasses.
    direct_rule(
        "temperature",
        auth_modes=_AUTH,
        schema=ANTHROPIC_TEMPERATURE_SCHEMA,
        projection_revision=_REVISION,
    ),
    # direct: proven through the installed AnthropicConfig transform (body top-level).
    direct_rule(
        "max_tokens",
        auth_modes=_AUTH,
        schema=MAX_TOKENS_SCHEMA,
        projection_revision=_REVISION,
    ),
    direct_rule(
        "top_p",
        auth_modes=_AUTH,
        schema=TOP_P_SCHEMA,
        projection_revision=_REVISION,
    ),
    # provider_native: Anthropic-native top_k (NOT an OpenAI param) projected to the
    # top level; api-key only (see module docstring). Proven through the installed
    # transform + litellm.get_optional_params delivery.
    provider_native_rule(
        "provider_params.top_k",
        provider_target="top_k",
        auth_modes=_API_KEY_ONLY,
        schema=TOP_K_SCHEMA,
        projection_revision=_REVISION,
    ),
)


def anthropic_chat_parameter_rules(
    *, model: str, auth_type: AuthType | None = None
) -> tuple[ParameterProjectionRule, ...]:
    return _RULES
