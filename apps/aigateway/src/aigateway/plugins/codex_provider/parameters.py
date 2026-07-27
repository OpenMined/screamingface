"""Codex chat-parameter rules (OME-634, OME-479 §Phase 9) — proven set only.

Codex is NOT an OpenAI Chat Completions provider. It rides the ChatGPT subscription
Responses endpoint, and ``chat_handler._build_payload`` — the last AIGateway-owned
boundary before that wire — copies only a FIXED set of keys out of
``optional_params`` (``tools``, ``tool_choice``, ``reasoning``,
``previous_response_id``, ``truncation``, plus a merged ``include``). Everything else
is DROPPED before the request leaves the gateway.

INVARIANT (§9): a rule is earned only by proving the value survives that copy. That
makes the enabled set deliberately narrow — and the narrowness is the honest report,
not an oversight:

- ``reasoning_effort`` IS enabled. ``plugin.prepare_chat_body`` converts it to
  ``reasoning: {"effort": …}``, which ``_build_payload`` carries. The conversion
  already existed; without this rule the classifier rejected the field first, so it
  was unreachable.
- Sampling (``temperature``, ``top_p``, ``max_tokens``) is NOT enabled. The transform
  drops it, so a rule would accept the caller's value and silently discard it. A
  refusal the caller can see beats a promise the wire never keeps.
- ``tools``/``tool_choice`` are NOT enabled. ``_build_payload`` forwards a caller's
  array VERBATIM, but the two tool shapes are not interchangeable: Chat Completions
  nests the definition under ``function``, the Responses API expects it flattened
  beside ``type`` (litellm 1.87.0's own converter,
  ``responses/litellm_completion_transformation/transformation.py``, is the
  authority). Function calling here needs a shape adapter in the transform first.
- ``previous_response_id`` is NOT enabled: the payload hardcodes ``store: False``, so
  no response is ever persisted to continue from.

# AIDEV-NOTE: adding a rule here is only half the work — check ``_build_payload``
# first. If the key is not in its copy list, the value dies inside the gateway.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import (
    ParameterProjectionRule,
    ProviderParameterObservation,
)
from aigateway.core.profile_models import AuthType
from aigateway.core.standard_parameters import (
    REASONING_EFFORT_SCHEMA,
    direct_parameter_observations,
    direct_rule,
)

# The Responses endpoint publishes no machine-readable schema to the gateway, so the
# only honest evidence is the reviewed transform mapping, under Codex's own label.
RESPONSES_SOURCE = "codex:responses"

# OAuth-only: the handler rejects sk-/sk-proj- keys outright, and the plugin exposes
# no api-key strategy, so there is no second mode to rule for.
_AUTH: tuple[AuthType, ...] = ("oauth",)
# Bump when a projection's semantics change; folds into the contract digests.
_REVISION = "codex-2026-07"

_ENABLED_PATHS: tuple[str, ...] = ("reasoning_effort",)

_RULES: tuple[ParameterProjectionRule, ...] = (
    # WHY the SHARED effort ladder rather than a Codex-local narrowing: rejecting a
    # value the provider would accept is the failure mode this work exists to remove.
    # An effort a specific model declines fails upstream with the provider's own
    # message — the milder outcome, and one the gateway cannot get wrong as models move.
    direct_rule(
        "reasoning_effort",
        auth_modes=_AUTH,
        schema=REASONING_EFFORT_SCHEMA,
        projection_revision=_REVISION,
    ),
)

# §4.4: every enabled path carries evidence.
# INVARIANT: an observation NEVER enables a parameter — only a rule does.
CODEX_OBSERVATIONS: tuple[ProviderParameterObservation, ...] = direct_parameter_observations(
    _ENABLED_PATHS, source=RESPONSES_SOURCE
)


def codex_chat_parameter_rules(
    *, model: str, auth_type: AuthType | None = None
) -> tuple[ParameterProjectionRule, ...]:
    """The proven rule set is identical for every Codex model; auth-mode filtering is
    applied by the core classifier/contract, not here."""
    return _RULES
