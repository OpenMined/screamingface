"""Anthropic reasoning/max-token cross-field rule (OME-479 §4.5, OME-640).

FEATURE: one effective parameter contract. ``reasoning_effort`` and ``max_tokens``
each validate alone, but on a MANUAL-thinking model the installed transform turns
the effort into a thinking BUDGET, and Anthropic's Messages API requires that
budget to be smaller than ``max_tokens``. So the pair has to be refused where the
contract is decided, not discovered as an opaque provider error after dispatch.

INVARIANT: this is the ONLY place the constraint lives. It is provider-local by
design — ``core/parameter_projection.py`` carries a "no provider-name switch"
invariant, so the model list, the budget ladder and the auth split all stay here
and reach the route through the ``validate_chat_parameter_combination`` hook.

Three facts, each measured against the INSTALLED litellm and each pinned by a
test in ``tests/unit/anthropic/test_anthropic_thinking_conflict.py``:

1. ``AnthropicConfig._map_reasoning_effort`` branches on
   ``_is_adaptive_thinking_model(model)`` BEFORE it reads the effort value. The
   three adaptive models therefore emit ``thinking={"type":"adaptive"}`` with no
   budget at all — the constraint does not exist for them and applying it would
   refuse legal requests on most of the fleet.
2. ``BaseConfig.update_optional_params_with_thinking_tokens`` raises ``max_tokens``
   above the budget itself, but ONLY when the caller supplied none. So the invalid
   pair is reachable exactly when ``max_tokens`` is present.
3. The exemption is auth-shaped, and the split lives in the credential layer:
   ``AnthropicOAuth._build_headers`` sends ``anthropic-beta`` including
   ``interleaved-thinking-2025-05-14``; the api-key path sends no beta header at
   all. Under interleaved thinking the budget may exceed ``max_tokens`` — but
   interleaved thinking is defined as extended thinking WITH TOOL USE, so the
   header alone is not enough.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aigateway.core.model_parameter_contract import upstream_model_id
from aigateway.core.parameter_projection import IncompatibleParametersError
from aigateway.core.profile_models import AuthMode

# The two registered models the installed transform still maps to a manual
# thinking BUDGET. Everything else Anthropic registers is adaptive.
MANUAL_THINKING_MODELS: frozenset[str] = frozenset(
    {
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
    }
)

# effort -> thinking.budget_tokens, over the gateway's own REASONING_EFFORT_SCHEMA
# enum. ``none`` maps to no thinking and so has no entry. litellm also defines
# ``xhigh``/``max``, which the gateway schema rejects earlier.
MANUAL_THINKING_BUDGETS: dict[str, int] = {
    "minimal": 1024,
    "low": 1024,
    "medium": 2048,
    "high": 4096,
}

# Manual-thinking models for which the OAuth beta header actually lifts the
# constraint.
# AIDEV-NOTE: Haiku 4.5 is deliberately absent. The published documentation groups
# it with Opus 4.5 as having "different interleaved thinking behaviors" without
# saying what they are, so this takes the fail-closed reading. Being wrong here
# costs an honest 400 on a pair that is invalid on the api-key path regardless;
# being wrong the other way costs an opaque provider error after dispatch. Promote
# it only on positive evidence that the header is honored.
INTERLEAVED_BETA_MODELS: frozenset[str] = frozenset({"claude-sonnet-4-5"})

_CONFLICT_PATHS = ("reasoning_effort", "max_tokens")


def _has_tools(body: Mapping[str, Any]) -> bool:
    # An EMPTY array is a valid ``tools`` value that engages no tool, so it cannot
    # bring a tool-use feature into effect.
    tools = body.get("tools")
    return isinstance(tools, list) and len(tools) > 0


def _budget_applies(model_id: str, *, auth_mode: AuthMode, body: Mapping[str, Any]) -> bool:
    if model_id not in MANUAL_THINKING_MODELS:
        return False
    interleaved = auth_mode == "oauth" and model_id in INTERLEAVED_BETA_MODELS and _has_tools(body)
    return not interleaved


def raise_on_thinking_conflict(body: Mapping[str, Any], *, model: str, auth_mode: AuthMode) -> None:
    """Refuse a thinking budget that ``max_tokens`` leaves no room for.

    # INVARIANT: the model table is a CLOSED WORLD of reviewed registered ids. An
    # unrecognized id is left alone — guessing "manual" would refuse a legal
    # request on a model nobody has looked at, which is the one failure mode this
    # check must not have.
    """
    effort = body.get("reasoning_effort")
    max_tokens = body.get("max_tokens")
    if not isinstance(effort, str) or not isinstance(max_tokens, int):
        return
    budget = MANUAL_THINKING_BUDGETS.get(effort)
    if budget is None:
        # "none" (and anything the schema did not admit) requests no thinking.
        return
    model_id = upstream_model_id(model)
    if not _budget_applies(model_id, auth_mode=auth_mode, body=body):
        return
    if max_tokens > budget:
        return
    raise IncompatibleParametersError(
        _CONFLICT_PATHS,
        reason=(
            f"reasoning_effort={effort!r} requests a {budget}-token thinking budget on "
            f"{model_id}, and this model requires max_tokens to be greater than the "
            f"thinking budget"
        ),
    )
