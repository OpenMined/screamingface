from __future__ import annotations

from aigateway.core.chat_parameters import ParameterProjectionRule
from aigateway.core.profile_models import AuthMode
from aigateway.core.standard_parameters import MAX_TOKENS_SCHEMA, direct_rule

_AUTH: tuple[AuthMode, ...] = ("api_key",)
_REVISION = "openai-2026-08-p0"

_RULES: tuple[ParameterProjectionRule, ...] = (
    direct_rule(
        "max_tokens",
        auth_modes=_AUTH,
        schema=MAX_TOKENS_SCHEMA,
        cache_behavior="bypass",
        projection_revision=_REVISION,
    ),
)


def openai_chat_parameter_rules(
    *, model: str, auth_type: AuthMode | None = None
) -> tuple[ParameterProjectionRule, ...]:
    del model, auth_type
    return _RULES
