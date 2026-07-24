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

from aigateway.core.chat_parameters import ParameterProjectionRule
from aigateway.core.profile_models import AuthType
from aigateway.core.standard_parameters import (
    MAX_TOKENS_SCHEMA,
    TEMPERATURE_SCHEMA,
    TOP_K_SCHEMA,
    direct_rule,
    provider_native_rule,
)

# OpenRouter is API-key only (no OAuth); its auth-mode intersection is a single
# mode, so every proven rule is enabled under it.
_AUTH: tuple[AuthType, ...] = ("api_key",)
# Bump when a projection's semantics change; folds into the contract digests.
_REVISION = "openrouter-2026-07"

_RULES: tuple[ParameterProjectionRule, ...] = (
    direct_rule(
        "temperature", auth_modes=_AUTH, schema=TEMPERATURE_SCHEMA, projection_revision=_REVISION
    ),
    direct_rule(
        "max_tokens", auth_modes=_AUTH, schema=MAX_TOKENS_SCHEMA, projection_revision=_REVISION
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
        schema=TOP_K_SCHEMA,
        projection_revision=_REVISION,
    ),
)


def openrouter_chat_parameter_rules(
    *, model: str, auth_type: AuthType | None = None
) -> tuple[ParameterProjectionRule, ...]:
    """The proven rule set is identical for every OpenRouter model; auth-mode
    filtering is applied by the core classifier/contract, not here."""
    return _RULES
