"""Fail-closed construction rules for provider parameter projections."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aigateway.core.chat_parameters import (
    DuplicateParameterRuleError,
    InvalidParameterRuleError,
    ParameterProjectionRule,
    ParameterSchema,
    normalize_rules,
)
from aigateway.core.parameter_projection import (
    GATEWAY_OWNED_FIELDS,
    classify_and_project_chat_parameters,
)

_SCHEMA = ParameterSchema(type="string")


def _rule(request_path: str, target: str) -> ParameterProjectionRule:
    return ParameterProjectionRule(
        request_path=request_path,
        schema=_SCHEMA,
        applicable_auth_modes=("api_key",),
        projection_kind="provider_native",
        provider_target=target,
        cache_behavior="bypass",
        projection_revision="test-v1",
    )


@pytest.mark.parametrize(
    ("alpha_target", "beta_target"),
    [("envelope", "envelope.inner"), ("envelope.inner", "envelope")],
)
def test_prefix_related_provider_targets_are_rejected(alpha_target: str, beta_target: str) -> None:
    rules = (
        _rule("provider_params.alpha", alpha_target),
        _rule("provider_params.beta", beta_target),
    )

    with pytest.raises(DuplicateParameterRuleError, match="prefix-related provider targets"):
        normalize_rules(rules)


def test_sibling_provider_targets_remain_valid() -> None:
    rules = (
        _rule("provider_params.alpha", "envelope.first"),
        _rule("provider_params.beta", "envelope.second"),
    )

    assert normalize_rules(rules) == rules


@pytest.mark.parametrize(
    "target",
    [target for field in sorted(GATEWAY_OWNED_FIELDS) for target in (field, f"{field}.nested")],
)
def test_rule_cannot_target_a_gateway_owned_field_or_descendant(target: str) -> None:
    with pytest.raises(ValidationError, match="gateway-owned field"):
        _rule("provider_params.value", target)


def test_direct_gateway_transport_rule_remains_valid() -> None:
    rule = ParameterProjectionRule(
        request_path="stream",
        schema=_SCHEMA,
        applicable_auth_modes=("api_key",),
        projection_kind="direct",
        cache_behavior="transport_only",
        output_affecting=False,
        projection_revision="test-v1",
    )

    assert rule.target == "stream"


def test_provider_params_wrapper_target_fails_closed_without_assert() -> None:
    rule = _rule("provider_params.value", "provider_params")

    with pytest.raises(InvalidParameterRuleError, match="provider_params wrapper"):
        classify_and_project_chat_parameters(
            {"provider_params": {"value": "unsafe"}},
            rules=(rule,),
            auth_mode="api_key",
        )
