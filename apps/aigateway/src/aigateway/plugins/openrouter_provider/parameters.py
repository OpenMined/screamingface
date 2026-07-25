"""OpenRouter chat-parameter rules (OME-479 §6.1) — currently-proven set only.

INVARIANT: every rule here is backed by a capture/boundary test proving the
field reaches OpenRouter dispatch, so enabling it is earned, not speculative
(plan §12). Standard sampling fields are ``direct``; OpenRouter-native routing
controls sent bare at the top level are classified individually as ``direct``
passthrough; ``top_k`` — not a standard OpenAI param for OpenRouter — is the P0
promotion, projected through ``extra_body`` where the installed litellm
transform carries it onto the wire (proven in tests).
"""

from __future__ import annotations

from aigateway.core.chat_parameters import (
    ParameterProjectionRule,
    ParameterSchema,
    ToolCapability,
)
from aigateway.core.profile_models import AuthType
from aigateway.core.standard_parameters import (
    LOGPROBS_SCHEMA,
    MAX_TOKENS_SCHEMA,
    N_SCHEMA,
    PENALTY_SCHEMA,
    RESPONSE_FORMAT_SCHEMA,
    SEED_SCHEMA,
    STOP_SCHEMA,
    TEMPERATURE_SCHEMA,
    TOP_LOGPROBS_SCHEMA,
    direct_rule,
    function_calling_rules,
    provider_native_rule,
)

# OpenRouter is API-key only (no OAuth); its auth-mode intersection is a single
# mode, so every proven rule is enabled under it.
_AUTH: tuple[AuthType, ...] = ("api_key",)
# Bump when a projection's semantics change; folds into the contract digests.
_REVISION = "openrouter-2026-07"

# WHY: OpenRouter documents ``top_k`` as an integer "0 or above" (0 disables top-k
# sampling) and the installed litellm transform forwards 0 verbatim (§9 probe), so
# OpenRouter binds its OWN minimum=0 schema. Do NOT widen the shared ``TOP_K_SCHEMA``
# (minimum=1) — Anthropic and Gemini still bind it and their top-k lower bound is 1.
OPENROUTER_TOP_K_SCHEMA = ParameterSchema(type="integer", minimum=0)

# OME-583: OpenRouter is OpenAI-compatible; the INSTALLED litellm openrouter transform
# forwards tools[] and tool_choice onto the wire (§9), so function calling is enabled
# WITH tool_choice.
_TOOL_CAPABILITIES: tuple[ToolCapability, ...] = (
    ToolCapability(tool_type="function", provider_support="supported", gateway_status="enabled"),
)

_RULES: tuple[ParameterProjectionRule, ...] = (
    direct_rule(
        "temperature", auth_modes=_AUTH, schema=TEMPERATURE_SCHEMA, projection_revision=_REVISION
    ),
    direct_rule(
        "max_tokens", auth_modes=_AUTH, schema=MAX_TOKENS_SCHEMA, projection_revision=_REVISION
    ),
    # direct: standard stop (string | array[string]); the installed litellm OpenRouter
    # path forwards it as the OpenAI-native `stop` (proven in test_openrouter_dispatch).
    direct_rule("stop", auth_modes=_AUTH, schema=STOP_SCHEMA, projection_revision=_REVISION),
    # OME-584: structured output. The installed litellm OpenRouter transform forwards
    # response_format VERBATIM (§9 probe: both json_object and json_schema reach the wire
    # unchanged), so it is a direct passthrough gated by the shared response-format schema.
    direct_rule(
        "response_format",
        auth_modes=_AUTH,
        schema=RESPONSE_FORMAT_SCHEMA,
        projection_revision=_REVISION,
    ),
    # OME-585: seed + n sampling controls. The installed litellm OpenRouter transform
    # forwards both VERBATIM (§9 probe), so each is a direct passthrough gated by its
    # bounded integer schema (seed: any int; n: >= 1).
    direct_rule("seed", auth_modes=_AUTH, schema=SEED_SCHEMA, projection_revision=_REVISION),
    direct_rule("n", auth_modes=_AUTH, schema=N_SCHEMA, projection_revision=_REVISION),
    # OME-586: frequency_penalty + presence_penalty repetition controls. The installed
    # litellm OpenRouter transform forwards both VERBATIM (§9 probe), so each is a direct
    # passthrough gated by the shared [-2, 2] penalty schema.
    direct_rule(
        "frequency_penalty", auth_modes=_AUTH, schema=PENALTY_SCHEMA, projection_revision=_REVISION
    ),
    direct_rule(
        "presence_penalty", auth_modes=_AUTH, schema=PENALTY_SCHEMA, projection_revision=_REVISION
    ),
    # OME-595: logprobs + top_logprobs output-introspection controls. The installed litellm
    # OpenRouter transform forwards both VERBATIM (§9 probe), so each is a direct passthrough:
    # logprobs gated as a boolean, top_logprobs as a bounded integer (0..20).
    direct_rule(
        "logprobs", auth_modes=_AUTH, schema=LOGPROBS_SCHEMA, projection_revision=_REVISION
    ),
    direct_rule(
        "top_logprobs", auth_modes=_AUTH, schema=TOP_LOGPROBS_SCHEMA, projection_revision=_REVISION
    ),
    # WHY: OpenRouter-native routing controls are complex nested values with no
    # scalar schema; a schema-less rule authorizes the path and forwards the
    # value verbatim, preserving existing client behavior under fail-closed.
    direct_rule("provider", auth_modes=_AUTH, projection_revision=_REVISION),
    direct_rule("plugins", auth_modes=_AUTH, projection_revision=_REVISION),
    direct_rule("route", auth_modes=_AUTH, projection_revision=_REVISION),
    direct_rule("models", auth_modes=_AUTH, projection_revision=_REVISION),
    provider_native_rule(
        "provider_params.top_k",
        provider_target="extra_body.top_k",
        auth_modes=_AUTH,
        schema=OPENROUTER_TOP_K_SCHEMA,
        projection_revision=_REVISION,
    ),
    # OME-583: tools + tool_choice (OpenAI-native, §9 proof).
    *function_calling_rules(_TOOL_CAPABILITIES, auth_modes=_AUTH, projection_revision=_REVISION),
)


def openrouter_chat_parameter_rules(
    *, model: str, auth_type: AuthType | None = None
) -> tuple[ParameterProjectionRule, ...]:
    """The proven rule set is identical for every OpenRouter model; auth-mode
    filtering is applied by the core classifier/contract, not here."""
    return _RULES


def openrouter_chat_parameter_tools(
    *, model: str, auth_type: AuthType | None = None
) -> tuple[ToolCapability, ...]:
    # OME-583: the accepted tools[].type discriminator(s); drives supported_tools +
    # the detail contract's tools section.
    return _TOOL_CAPABILITIES
