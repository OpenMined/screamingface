"""Fail-closed validation for non-finite JSON numeric parameters."""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aigateway.core.chat_parameters import (
    ParameterProjectionRule,
    ParameterSchema,
    ParameterValidationError,
)
from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_number_schema_rejects_every_non_finite_float(value: float) -> None:
    schema = ParameterSchema(type="number")

    with pytest.raises(ParameterValidationError, match="finite"):
        schema.validate_value(value)


@pytest.mark.parametrize("value", [-1e308, -1.0, 0.0, 1.0, 1e308])
def test_number_schema_preserves_finite_values(value: float) -> None:
    schema = ParameterSchema(type="number")

    schema.validate_value(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_classifier_reports_non_finite_values_as_malformed(value: float) -> None:
    rule = ParameterProjectionRule(
        request_path="temperature",
        schema=ParameterSchema(type="number", minimum=0.0, maximum=2.0),
        applicable_auth_modes=("none",),
        projection_kind="direct",
        cache_behavior="bypass",
        projection_revision="finite-v1",
    )

    with pytest.raises(UnsupportedParametersError) as exc_info:
        classify_and_project_chat_parameters(
            {"temperature": value},
            rules=(rule,),
            auth_mode="none",
        )

    assert exc_info.value.rejected == {"temperature": "malformed"}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_numeric_array_schema_rejects_non_finite_items(value: float) -> None:
    schema = ParameterSchema(type="array", item_type="number")

    with pytest.raises(ParameterValidationError, match="finite"):
        schema.validate_value([0.0, value])


def test_classifier_reports_non_finite_numeric_array_item_as_malformed() -> None:
    rule = ParameterProjectionRule(
        request_path="scores",
        schema=ParameterSchema(type="array", item_type="number"),
        applicable_auth_modes=("none",),
        projection_kind="direct",
        cache_behavior="bypass",
        projection_revision="finite-v1",
    )

    with pytest.raises(UnsupportedParametersError) as exc_info:
        classify_and_project_chat_parameters(
            {"scores": [1.0, float("nan")]},
            rules=(rule,),
            auth_mode="none",
        )

    assert exc_info.value.rejected == {"scores": "malformed"}


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_chat_route_rejects_non_finite_json_before_dispatch(
    authenticated_client, literal: str
) -> None:
    dispatched: list[dict] = []

    async def fake_acompletion(**kwargs):
        dispatched.append(kwargs)
        return SimpleNamespace(model_dump=lambda: {"id": "unexpected"})

    payload = (
        '{"model":"ollama/non-finite","messages":'
        '[{"role":"user","content":"hi"}],"temperature":'
        f"{literal}" + "}"
    )
    with patch("litellm.acompletion", fake_acompletion):
        response = authenticated_client.post(
            "/v1/chat/completions",
            content=payload,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "unsupported_parameters"
    assert detail["rejected"] == {"temperature": "malformed"}
    assert dispatched == []
    assert math.isfinite(float(literal)) is False
