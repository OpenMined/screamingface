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
# seed, stop) are OBSERVED (labelled-static) but deliberately left UNRULED in v1 —
# they surface visible-but-disabled. Promote one only by adding its rule here with
# a matching installed-transform characterization test (purely additive).
"""

from __future__ import annotations

from aigateway.core.chat_parameters import ParameterProjectionRule
from aigateway.core.profile_models import AuthType
from aigateway.core.standard_parameters import (
    MAX_TOKENS_SCHEMA,
    TEMPERATURE_SCHEMA,
    direct_rule,
)

# HF is API-key only (no OAuth); the auth-mode intersection is a single mode, so
# every proven rule is enabled under it.
_AUTH: tuple[AuthType, ...] = ("api_key",)
# Bump when a projection's semantics change; folds into the contract digests.
_REVISION = "huggingface-2026-07"

_RULES: tuple[ParameterProjectionRule, ...] = (
    direct_rule(
        "temperature", auth_modes=_AUTH, schema=TEMPERATURE_SCHEMA, projection_revision=_REVISION
    ),
    direct_rule(
        "max_tokens", auth_modes=_AUTH, schema=MAX_TOKENS_SCHEMA, projection_revision=_REVISION
    ),
)


def huggingface_chat_parameter_rules(
    *, model: str, auth_type: AuthType | None = None
) -> tuple[ParameterProjectionRule, ...]:
    """The proven rule set is identical for every HF model; auth-mode filtering is
    applied by the core classifier/contract, not here."""
    return _RULES
