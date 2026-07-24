"""Reusable OpenAI-compatible parameter schemas + rule builders (OME-479 §4.2).

Provider plugins SELECT from these to compose their own rule sets. Defining the
bounded schema for a standard field ONCE stops providers from disagreeing about
what ``temperature`` means, while each plugin still owns which fields it enables,
under which auth modes, and where each value projects.

INVARIANT (SOLID/hexagonal): no provider names appear here. This module is the
shared vocabulary; the choice of which words to speak stays provider-local, so
enabling a new parameter is a provider-local edit, never a change here.
"""

from __future__ import annotations

from .chat_parameters import CacheBehavior, ParameterProjectionRule, ParameterSchema
from .profile_models import AuthType

# Bounded schemas for the standard OpenAI-compatible optional fields the gateway
# forwards; ranges follow the OpenAI Chat Completions contract.
TEMPERATURE_SCHEMA = ParameterSchema(type="number", minimum=0, maximum=2)
TOP_P_SCHEMA = ParameterSchema(type="number", minimum=0, maximum=1)
MAX_TOKENS_SCHEMA = ParameterSchema(type="integer", minimum=1)
TOP_K_SCHEMA = ParameterSchema(type="integer", minimum=1)
# Union of the OpenAI reasoning-effort ladder and Anthropic's "none" (disable
# thinking); a value outside this set fails closed at classification.
REASONING_EFFORT_SCHEMA = ParameterSchema(
    type="string", enum=("none", "minimal", "low", "medium", "high")
)
# ``stop`` is the OpenAI top-level UNION string | array[string]: a single stop
# string, or an array of them. The scalar form skips item validation; the array
# form requires every item to be a string, so a wrong-typed item (e.g. [123])
# fails closed as malformed at classification, before any credential access.
STOP_SCHEMA = ParameterSchema(type=("string", "array"), item_type="string")


def direct_rule(
    request_path: str,
    *,
    auth_modes: tuple[AuthType, ...],
    projection_revision: str,
    schema: ParameterSchema | None = None,
    provider_target: str | None = None,
    cache_behavior: CacheBehavior = "bypass",
    output_affecting: bool = True,
) -> ParameterProjectionRule:
    """A standard field kept on the request under ``request_path`` (or a target)."""
    return ParameterProjectionRule(
        request_path=request_path,
        applicable_auth_modes=auth_modes,
        projection_kind="direct",
        provider_target=provider_target,
        cache_behavior=cache_behavior,
        output_affecting=output_affecting,
        projection_revision=projection_revision,
        schema=schema,
    )


def provider_native_rule(
    request_path: str,
    *,
    provider_target: str,
    auth_modes: tuple[AuthType, ...],
    projection_revision: str,
    schema: ParameterSchema | None = None,
    cache_behavior: CacheBehavior = "bypass",
    output_affecting: bool = True,
) -> ParameterProjectionRule:
    """A ``provider_params.*`` field projected to a provider-native ``target``."""
    return ParameterProjectionRule(
        request_path=request_path,
        applicable_auth_modes=auth_modes,
        projection_kind="provider_native",
        provider_target=provider_target,
        cache_behavior=cache_behavior,
        output_affecting=output_affecting,
        projection_revision=projection_revision,
        schema=schema,
    )
