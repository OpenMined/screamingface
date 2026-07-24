"""Hugging Face chat-parameter rules (OME-479 §6.2) — currently-proven set only.

INVARIANT: every rule here is backed by a characterization test that runs the
INSTALLED litellm ``HuggingFaceChatConfig`` transform and proves the field reaches
the outbound provider body — so enabling it is earned, not speculative (plan §12;
§6.2 "seed enabled rules only from behavior proven through the installed final
transform"). HF's router is OpenAI-compatible, so these standard sampling fields
are ``direct`` passthrough. HF has NO OAuth, so the auth-mode intersection is a
single ``api_key`` mode. Backend-conditional TOOL/structured-output support is
separate catalog evidence and never enables an ordinary parameter here.

# AIDEV-NOTE: broader sampling fields (top_p, frequency_penalty, presence_penalty,
# seed) are OBSERVED (labelled-static) but deliberately left UNRULED in v1 — they
# surface visible-but-disabled. Promote one only by adding its rule here with a
# matching installed-transform characterization test (purely additive). ``stop`` is
# now ruled (string | array[string]); the installed transform forwards it verbatim.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import ParameterProjectionRule, ToolCapability
from aigateway.core.profile_models import AuthType
from aigateway.core.standard_parameters import (
    MAX_TOKENS_SCHEMA,
    STOP_SCHEMA,
    TEMPERATURE_SCHEMA,
    direct_rule,
    function_calling_rules,
)

# HF is API-key only (no OAuth); the auth-mode intersection is a single mode, so
# every proven rule is enabled under it.
_AUTH: tuple[AuthType, ...] = ("api_key",)
# Bump when a projection's semantics change; folds into the contract digests.
_REVISION = "huggingface-2026-07"

# OME-583: HF's router is OpenAI-compatible; the INSTALLED litellm HuggingFace transform
# forwards tools[] and tool_choice onto the wire (§9), so function calling is enabled WITH
# tool_choice. Backend-conditional catalog support (huggingface:router) is separate live
# evidence and does not enable this rule — the installed-transform proof does.
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
    # direct: standard stop (string | array[string]); the OpenAI-compatible HF router
    # forwards it verbatim through the installed transform (proven in the dispatch test).
    direct_rule("stop", auth_modes=_AUTH, schema=STOP_SCHEMA, projection_revision=_REVISION),
    # OME-583: tools + tool_choice (OpenAI-native, §9 installed-transform proof).
    *function_calling_rules(_TOOL_CAPABILITIES, auth_modes=_AUTH, projection_revision=_REVISION),
)


def huggingface_chat_parameter_rules(
    *, model: str, auth_type: AuthType | None = None
) -> tuple[ParameterProjectionRule, ...]:
    """The proven rule set is identical for every HF model; auth-mode filtering is
    applied by the core classifier/contract, not here."""
    return _RULES


def huggingface_chat_parameter_tools(
    *, model: str, auth_type: AuthType | None = None
) -> tuple[ToolCapability, ...]:
    # OME-583: the accepted tools[].type discriminator(s); drives supported_tools +
    # the detail contract's tools section.
    return _TOOL_CAPABILITIES
