"""Hugging Face chat-parameter rules (OME-479 §6.2) — currently-proven set only.

INVARIANT: every rule here is backed by a characterization test that runs the
INSTALLED litellm ``HuggingFaceChatConfig`` transform and proves the field reaches
the outbound provider body — so enabling it is earned, not speculative (plan §12;
§6.2 "seed enabled rules only from behavior proven through the installed final
transform"). HF's router is OpenAI-compatible, so these standard sampling fields
are ``direct`` passthrough. HF has NO OAuth, so the auth-mode intersection is a
single ``api_key`` mode. Backend-conditional TOOL/structured-output support is
separate catalog evidence and never enables an ordinary parameter here.

# AIDEV-NOTE: ``top_p`` is OBSERVED (labelled-static) but deliberately left UNRULED in
# v1 — it surfaces visible-but-disabled. Promote it only by adding its rule here with a
# matching installed-transform characterization test (purely additive). ``stop`` (string |
# array[string]), ``seed`` / ``n`` (OME-585), ``frequency_penalty`` / ``presence_penalty``
# (OME-586), and ``logprobs`` / ``top_logprobs`` (OME-595) are now ruled; the installed
# transform forwards each verbatim.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import (
    ParameterProjectionRule,
    ParameterSchema,
    ToolCapability,
)
from aigateway.core.profile_models import AuthMode
from aigateway.core.standard_parameters import (
    LOGPROBS_SCHEMA,
    MAX_TOKENS_SCHEMA,
    N_SCHEMA,
    PENALTY_SCHEMA,
    RESPONSE_FORMAT_SCHEMA,
    SEED_SCHEMA,
    STOP_SCHEMA,
    TEMPERATURE_SCHEMA,
    direct_rule,
    function_calling_rules,
)

# HF is API-key only (no OAuth); the auth-mode intersection is a single mode, so
# every proven rule is enabled under it.
_AUTH: tuple[AuthMode, ...] = ("api_key",)
# Bump when a projection's semantics change; folds into the contract digests.

# AIDEV-NOTE (OME-305, owner decision B — READ BEFORE CHANGING A ``cache_behavior``).
# Every rule below states ``cache_behavior="bypass"`` EXPLICITLY. That is a disposition,
# not an oversight, and it is not a judgement about the parameter: each of these values
# is output-affecting and WOULD have to be keyed for a cached answer to be correct.
#
# The reason they are not keyed is that THIS PROVIDER DOES NOT IMPLEMENT
# ``global_cache_projection`` — it inherits the ``CacheBypass`` default from
# ``ProviderPluginBase``. While that is true, every request to this provider bypasses
# the cache at the projection step regardless of any rule, so declaring ``keyed`` here
# would change no behaviour while advertising a cacheable parameter to callers that can
# never be cached. ``test_a_provider_that_declares_a_keyed_rule_backs_it_with_a_real_projection``
# in ``tests/unit/test_global_cache_registry_conformance.py`` is what enforces that.
#
# TO PROMOTE THESE: implement ``global_cache_projection`` for this provider FIRST, then
# flip these to ``keyed`` in the same change. The order matters — the conformance sweep
# will refuse the flip on its own, which is the intended guard rail rather than an
# obstacle. Anthropic and OpenRouter are the two providers that have the projection and
# therefore carry keyed rules today.

_REVISION = "huggingface-2026-07"

_HF_TOP_LOGPROBS_SCHEMA = ParameterSchema(
    type="integer",
    minimum=0,
    maximum=5,
)

# OME-583: HF's router is OpenAI-compatible; the INSTALLED litellm HuggingFace transform
# forwards tools[] and tool_choice onto the wire (§9), so function calling is enabled WITH
# tool_choice. Backend-conditional catalog support (huggingface:router) is separate live
# evidence and does not enable this rule — the installed-transform proof does.
_TOOL_CAPABILITIES: tuple[ToolCapability, ...] = (
    ToolCapability(tool_type="function", provider_support="supported", gateway_status="enabled"),
)

_RULES: tuple[ParameterProjectionRule, ...] = (
    direct_rule(
        "temperature",
        auth_modes=_AUTH,
        schema=TEMPERATURE_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    direct_rule(
        "max_tokens",
        auth_modes=_AUTH,
        schema=MAX_TOKENS_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    # direct: standard stop (string | array[string]); the OpenAI-compatible HF router
    # forwards it verbatim through the installed transform (proven in the dispatch test).
    direct_rule(
        "stop",
        auth_modes=_AUTH,
        schema=STOP_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    # OME-584: structured output. The installed HuggingFaceChatConfig transform forwards
    # response_format VERBATIM (§9 probe: both json_object and json_schema reach the wire
    # unchanged), so it is a direct passthrough gated by the shared response-format schema.
    direct_rule(
        "response_format",
        auth_modes=_AUTH,
        schema=RESPONSE_FORMAT_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    # OME-585: seed + n sampling controls. The installed HuggingFaceChatConfig transform
    # forwards both VERBATIM (§9 probe), so each is a direct passthrough gated by its
    # bounded integer schema (seed: any int; n: >= 1).
    direct_rule(
        "seed",
        auth_modes=_AUTH,
        schema=SEED_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    direct_rule(
        "n",
        auth_modes=_AUTH,
        schema=N_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    # OME-586: frequency_penalty + presence_penalty repetition controls. The installed
    # HuggingFaceChatConfig transform forwards both VERBATIM (§9 probe), so each is a direct
    # passthrough gated by the shared [-2, 2] penalty schema.
    direct_rule(
        "frequency_penalty",
        auth_modes=_AUTH,
        schema=PENALTY_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    direct_rule(
        "presence_penalty",
        auth_modes=_AUTH,
        schema=PENALTY_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    # OME-595: logprobs + top_logprobs output-introspection controls. The installed
    # HuggingFaceChatConfig transform forwards both VERBATIM (§9 probe), so each is a direct
    # passthrough: logprobs gated as a boolean, top_logprobs as HF's documented 0..5.
    direct_rule(
        "logprobs",
        auth_modes=_AUTH,
        schema=LOGPROBS_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    direct_rule(
        "top_logprobs",
        auth_modes=_AUTH,
        schema=_HF_TOP_LOGPROBS_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
    # OME-583: tools + tool_choice (OpenAI-native, §9 installed-transform proof).
    *function_calling_rules(_TOOL_CAPABILITIES, auth_modes=_AUTH, projection_revision=_REVISION),
)


def huggingface_chat_parameter_rules(
    *, model: str, auth_type: AuthMode | None = None
) -> tuple[ParameterProjectionRule, ...]:
    """The proven rule set is identical for every HF model; auth-mode filtering is
    applied by the core classifier/contract, not here."""
    return _RULES


def huggingface_chat_parameter_tools(
    *, model: str, auth_type: AuthMode | None = None
) -> tuple[ToolCapability, ...]:
    # OME-583: the accepted tools[].type discriminator(s); drives supported_tools +
    # the detail contract's tools section.
    return _TOOL_CAPABILITIES
