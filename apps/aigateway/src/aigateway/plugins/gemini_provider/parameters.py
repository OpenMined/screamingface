"""Gemini chat-parameter rules (OME-479 §Phase 9) — currently-proven set only.

INVARIANT: every rule here is backed by a characterization test that runs the
request pipeline and proves the value reaches ``build_generate_content_body``'s
``generationConfig`` — the last AIGateway-owned boundary that emits the Gemini
wire body — so enabling it is earned, not speculative (plan §12; §6.2). Both
dispatch paths (direct ``generateContent`` and the OAuth Code Assist envelope)
call that SAME builder, so every rule applies under BOTH auth modes; there is no
param-level auth asymmetry to fabricate (contrast Anthropic's api-key-only top_k).

Two shapes of enabled field:

- STANDARD OpenAI sampling fields the builder's ``config_map`` renames
  (``temperature``, ``top_p`` → ``topP``, ``max_tokens`` → ``maxOutputTokens``) —
  kept on the request as ``direct`` rules at their identity path.
- The provider-NATIVE ``top_k`` (not an OpenAI param) — a ``provider_native`` rule
  from the ``provider_params.top_k`` wrapper to the top-level ``top_k`` key the
  builder's ``config_map`` reads (renamed to ``topK``).

# AIDEV-NOTE: ``stop`` is mapped by the builder (→ ``stopSequences``) but is
# deliberately left UNRULED in v1 — its OpenAI ``string | array[string]`` union
# cannot be expressed by the single-``type`` ``ParameterSchema``, and forcing one
# type would narrow the accepted surface dishonestly. It surfaces visible-but-
# disabled in the detail contract; promote it only once core gains union schemas.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import ParameterProjectionRule
from aigateway.core.profile_models import AuthType
from aigateway.core.standard_parameters import (
    MAX_TOKENS_SCHEMA,
    TEMPERATURE_SCHEMA,
    TOP_K_SCHEMA,
    TOP_P_SCHEMA,
    direct_rule,
    provider_native_rule,
)

# Gemini offers BOTH api-key (generativelanguage) and OAuth (Code Assist) auth; both
# paths run the same body builder, so every proven rule is enabled under both modes.
_AUTH: tuple[AuthType, ...] = ("api_key", "oauth")
# Bump when a projection's semantics change; folds into the contract digests.
_REVISION = "gemini-2026-07"

_RULES: tuple[ParameterProjectionRule, ...] = (
    direct_rule(
        "temperature", auth_modes=_AUTH, schema=TEMPERATURE_SCHEMA, projection_revision=_REVISION
    ),
    direct_rule("top_p", auth_modes=_AUTH, schema=TOP_P_SCHEMA, projection_revision=_REVISION),
    direct_rule(
        "max_tokens", auth_modes=_AUTH, schema=MAX_TOKENS_SCHEMA, projection_revision=_REVISION
    ),
    provider_native_rule(
        "provider_params.top_k",
        provider_target="top_k",
        auth_modes=_AUTH,
        schema=TOP_K_SCHEMA,
        projection_revision=_REVISION,
    ),
)


def gemini_chat_parameter_rules(
    *, model: str, auth_type: AuthType | None = None
) -> tuple[ParameterProjectionRule, ...]:
    """The proven rule set is identical for every Gemini model and every auth mode;
    auth-mode filtering is applied by the core classifier/contract, not here."""
    return _RULES
