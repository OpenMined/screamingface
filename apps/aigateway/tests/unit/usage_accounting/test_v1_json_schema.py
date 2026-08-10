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
    resource = files("aigateway.core.usage_accounting").joinpath("usage_accounting_v1.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _rendered_success() -> dict[str, Any]:
    collector = RequestAccountingCollector(
        provider="openrouter",
        requested_model="openrouter/x/y",
        transport="litellm_async_http_v1",
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
        dispatched=True,
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
        dispatched=False,
    )
    Draft202012Validator(_schema()).validate(metadata)


def test_schema_rejects_unknown_core_fields() -> None:
    metadata = deepcopy(_rendered_success())
    metadata["usage_accounting"]["attempts"][0]["provider_native_body"] = {
        "prompt": "must-not-cross"
    }
    with pytest.raises(ValidationError):
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
        dispatched=False,
    )
    Draft202012Validator(_schema()).validate(metadata)
