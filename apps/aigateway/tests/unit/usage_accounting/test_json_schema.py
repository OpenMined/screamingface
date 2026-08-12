"""Machine-readable Engine handoff schema stays synchronized with the renderer."""

from __future__ import annotations

import json
from copy import deepcopy
from importlib.resources import files
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError
from litellm.types.utils import ModelResponse, Usage

from aigateway.core.usage_accounting import ProviderUsageAccountingEvidence
from aigateway.core.usage_accounting._classify import FAILURE_CODES
from aigateway.core.usage_accounting._collector import RequestAccountingCollector
from aigateway.core.usage_accounting._render import render_aigw_metadata
from aigateway.plugins.anthropic_provider.usage_accounting import (
    cache_reference_from_cached as anthropic_cache_reference_from_cached,
)
from aigateway.plugins.openrouter_provider.usage_accounting import (
    cache_reference_from_cached,
    normalize_openrouter_usage_accounting,
)


def _schema() -> dict[str, Any]:
    resource = files("aigateway.core.usage_accounting").joinpath("usage_accounting.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _rendered_success() -> dict[str, Any]:
    collector = RequestAccountingCollector(
        provider="openrouter",
        requested_model="openrouter/x/y",
        transport="litellm_async_http",
    )
    collector.begin_dispatch()
    marker = object()
    collector.on_send_admitted(marker)
    raw = {
        "id": "gen-1",
        "model": "x/y",
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "cost": 0.0012},
    }
    collector.on_response_completed(marker, status=200, raw_evidence=raw)
    evidence: ProviderUsageAccountingEvidence = normalize_openrouter_usage_accounting(
        request_body={"model": "openrouter/x/y"},
        raw_response=raw,
        final_response=raw,
    )
    collector.apply_evidence(collector.open_records()[0][0], evidence)
    return render_aigw_metadata(
        collector=collector,
        supported=True,
        cache_status="miss",
        gateway_call_id=collector.gateway_call_id,
    )


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(_schema())


def test_real_openrouter_success_validates_against_the_handoff_schema() -> None:
    Draft202012Validator(_schema()).validate(_rendered_success())


def test_real_cache_reference_validates_against_the_handoff_schema() -> None:
    reference = cache_reference_from_cached(
        {"usage": {"prompt_tokens": 2, "completion_tokens": 1, "cost": 0.0012}}
    )
    metadata = render_aigw_metadata(
        collector=None,
        supported=True,
        cache_status="hit",
        gateway_call_id="call_" + "a" * 32,
        cache_reference=reference,
    )
    Draft202012Validator(_schema()).validate(metadata)


def test_schema_rejects_unknown_core_fields() -> None:
    metadata = deepcopy(_rendered_success())
    metadata["usage_accounting"]["attempts"][0]["provider_native_body"] = {
        "prompt": "must-not-cross"
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(_schema()).validate(metadata)


def test_schema_pins_the_closed_failure_code_vocabulary() -> None:
    failure_code = _schema()["$defs"]["attempt"]["properties"]["failure_code"]
    assert set(failure_code["oneOf"][0]["enum"]) == FAILURE_CODES


def test_schema_uses_the_33_fractional_digit_bound_for_every_money_surface() -> None:
    schema = _schema()
    expected = r"^(0|[1-9][0-9]{0,17})(\.[0-9]{0,32}[1-9])?$"
    assert schema["$defs"]["direct_cost"]["properties"]["amount"]["oneOf"][0]["pattern"] == expected
    assert (
        schema["$defs"]["extension_fact"]["allOf"][1]["then"]["properties"]["value"]["pattern"]
        == expected
    )
    assert schema["$defs"]["cost_subtotal"]["properties"]["amount"]["pattern"] == expected


def test_schema_accepts_33_fractional_digits_on_all_money_surfaces() -> None:
    amount = "0.123456789012345678901234567890123"
    metadata = _rendered_success()
    attempt = metadata["usage_accounting"]["attempts"][0]
    attempt["direct_cost"]["amount"] = amount
    attempt["provider_extensions"] = [
        {
            "namespace": "openrouter.response_usage",
            "facts": [
                {
                    "name": "cost_detail",
                    "kind": "decimal",
                    "value": amount,
                    "unit": None,
                    "source": "openrouter.usage.cost_details.cost_detail",
                }
            ],
            "truncated": False,
        }
    ]
    metadata["request_economics"]["known_direct_cost_subtotals"][0]["amount"] = amount

    Draft202012Validator(_schema()).validate(metadata)


def test_real_anthropic_converted_cache_reference_validates_with_positive_usage() -> None:
    cached = ModelResponse(
        id="msg_1",
        model="claude-haiku-4-5",
        choices=[],
        usage=Usage(
            prompt_tokens=130,
            completion_tokens=25,
            total_tokens=155,
            cache_creation_input_tokens=10,
            cache_read_input_tokens=20,
        ),
    ).model_dump()
    reference = anthropic_cache_reference_from_cached(cached)
    assert reference is not None
    assert reference.usage.input.total == 130
    metadata = render_aigw_metadata(
        collector=None,
        supported=True,
        cache_status="hit",
        gateway_call_id="call_" + "b" * 32,
        cache_reference=reference,
    )
    Draft202012Validator(_schema()).validate(metadata)


def test_accounting_taxonomy_has_no_version_suffixes() -> None:
    schema_text = json.dumps(_schema(), sort_keys=True)
    assert ".v1" not in schema_text
    assert "_v1" not in schema_text
