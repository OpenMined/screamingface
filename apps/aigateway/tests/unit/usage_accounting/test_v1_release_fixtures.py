"""Authoritative exact fixture matrix required before accounting v1 publication."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from aigateway.core.usage_accounting import (
    CacheReference,
    CacheWriteTTL,
    DirectCost,
    InputTokenUsage,
    OutputTokenUsage,
    PricingContext,
    ProviderAttemptRecord,
    ProviderExtension,
    TokenUsage,
)
from aigateway.core.usage_accounting._render import render_aigw_metadata
from aigateway.plugins.anthropic_provider.usage_accounting import (
    cache_reference_from_cached as anthropic_cache_reference_from_cached,
)
from aigateway.plugins.anthropic_provider.usage_accounting import (
    normalize_anthropic_usage_accounting,
)
from aigateway.plugins.huggingface_provider.plugin import HuggingFaceProviderPlugin
from aigateway.plugins.openrouter_provider.usage_accounting import (
    cache_reference_from_cached as openrouter_cache_reference_from_cached,
)
from aigateway.plugins.openrouter_provider.usage_accounting import (
    normalize_openrouter_usage_accounting,
)

_CALL_ID = "call_" + "f" * 32

_REQUIRED_METADATA_FIXTURES = {
    "openrouter_full_success",
    "openrouter_explicit_zero",
    "openrouter_missing_evidence",
    "openrouter_retry",
    "openrouter_failure_with_usage",
    "anthropic_full_cache_ttl_success",
    "anthropic_missing_cache_evidence",
    "anthropic_service_tier_tool_usage",
    "anthropic_cache_replay",
    "hidden_transport_resend",
    "gateway_overload_retry",
    "response_less_transport_failure",
    "conversion_failure",
    "unsupported_provider_miss",
    "cache_hit_reference",
    "bounds_overflow",
    "huggingface_pinned_backend",
    "huggingface_unpinned_backend",
}
_ROUTE_ONLY_ACCEPTANCE = {
    "non_negotiated_response_parity",
    "unknown_accounting_version_rejection",
}
_EXPECTED_FIXTURE_SHA256 = {
    "anthropic_cache_replay": ("47f47fd0399b82f4bfb92194bd35dbe1272f3680878d2957aef337df6481d640"),
    "anthropic_full_cache_ttl_success": (
        "bcbd4aebb88b6486024fc535073f86a451bfc57ffcc8294f7eeaa3118045cc01"
    ),
    "anthropic_missing_cache_evidence": (
        "f14d1aef70b8b75ca66932d28083294cfec57dd406333f3423855472fe94cefc"
    ),
    "anthropic_service_tier_tool_usage": (
        "740f490a4472bff4b49646096da22eb270067e928f58ca799f0ef6df588861ea"
    ),
    "bounds_overflow": ("4868302b4d7d4c857a7c566cb958fd00e7ad50975759d18fb26972c7e02b76e9"),
    "cache_hit_reference": ("814180f7f91e24cb6b7b063f965ba375b3d1dab9d935a75c5ea2c80e028a8093"),
    "conversion_failure": ("e88c1f913b6df36283230878acfa1215b6420088d274c91a790d7b3b4f823bed"),
    "gateway_overload_retry": ("914665862ce94e8da1908cdd385cbce118c3256143edd70a5675476b41cbfe9f"),
    "hidden_transport_resend": ("06aca182a14c962f4158087f26e4f05caf9928f3f102e6659ca7471180a7dc38"),
    "huggingface_pinned_backend": (
        "afe528ef1aea44f465d0b86bd14a6cfcbc7b5782b3ecd941cde9c2dbcaee3322"
    ),
    "huggingface_unpinned_backend": (
        "d6f616455b8cb25f6f65d8f72864282a9fd74d53e816cfd6598d51a0f84454f7"
    ),
    "openrouter_explicit_zero": (
        "6792f8ef32ab0af871b0471f5006495f4add9ea078c4f686eb6239c699b0125f"
    ),
    "openrouter_failure_with_usage": (
        "ae8076aafeb8ade6fb0d4136be052ba45f5db1d46170875abd9312faf7ecf5db"
    ),
    "openrouter_full_success": ("d2ae44b5f9d81d42dd6fbf1c40660305b9ab5331aa5773fe7a62bcbffd493841"),
    "openrouter_missing_evidence": (
        "507afc3005f65a730f6a8a7883e2a6921d8cdb50c816d1a2ebfa9594f729bee2"
    ),
    "openrouter_retry": ("06aca182a14c962f4158087f26e4f05caf9928f3f102e6659ca7471180a7dc38"),
    "response_less_transport_failure": (
        "267fa9a56ca3d79ceddf93d335933ea363a6175c2dcfc8a0c454241cb10413f6"
    ),
    "unsupported_provider_miss": (
        "0688aa1201c0403b8084062d01c27be623f6de70c188e07df298b53a84509ff5"
    ),
}


class _Collector:
    def __init__(
        self,
        records: tuple[ProviderAttemptRecord, ...],
        *,
        status: str = "complete",
    ) -> None:
        self._records = records
        self._status = status

    def records(self) -> tuple[ProviderAttemptRecord, ...]:
        return self._records

    def status(self) -> str:
        return self._status


def _schema() -> dict[str, Any]:
    resource = files("aigateway.core.usage_accounting").joinpath("usage_accounting_v1.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _usage(
    *,
    status: str = "complete",
    source: str = "provider_raw_response",
    input_total: int | None = 2,
    uncached: int | None = 2,
    cache_read: int | None = None,
    cache_write: int | None = None,
    cache_write_by_ttl: tuple[CacheWriteTTL, ...] = (),
    output_total: int | None = 1,
    reasoning: int | None = None,
) -> TokenUsage:
    return TokenUsage(
        status=status,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        input=InputTokenUsage(
            total=input_total,
            uncached=uncached,
            cache_read=cache_read,
            cache_write=cache_write,
            cache_write_by_ttl=cache_write_by_ttl,
        ),
        output=OutputTokenUsage(total=output_total, reasoning=reasoning),
    )


def _record(
    sequence: int,
    *,
    provider: str = "openrouter",
    dispatch_index: int = 1,
    attempt_index: int = 1,
    outcome: str = "succeeded",
    http_status: int | None = 200,
    latency_ms: int | None = 1,
    usage: TokenUsage | None = None,
    pricing_context: PricingContext | None = None,
    direct_cost: DirectCost | None = None,
    provider_extensions: tuple[ProviderExtension, ...] = (),
    failure_code: str | None = None,
    response_model: str | None = "fixture-model",
    provider_response_id: str | None = "",
) -> ProviderAttemptRecord:
    return ProviderAttemptRecord(
        attempt_id=f"attempt_{sequence:032x}",
        sequence=sequence,
        dispatch_index=dispatch_index,
        attempt_index=attempt_index,
        provider=provider,
        requested_model=f"{provider}/fixture-model",
        response_model=response_model,
        provider_response_id=(
            f"response-{sequence}" if provider_response_id == "" else provider_response_id
        ),
        transport="litellm_async_http_v1",
        outcome=outcome,  # type: ignore[arg-type]
        http_status=http_status,
        latency_ms=latency_ms,
        usage=usage or _usage(),
        pricing_context=pricing_context or PricingContext(),
        direct_cost=direct_cost
        or DirectCost.reported(
            amount="0.001",
            unit="openrouter_credits",
            source="openrouter.usage.cost",
        ),
        provider_extensions=provider_extensions,
        failure_code=failure_code,
    )


def _anthropic_record(
    sequence: int, raw_usage: dict[str, Any], **overrides: Any
) -> ProviderAttemptRecord:
    evidence = normalize_anthropic_usage_accounting(
        request_body={"model": "anthropic/fixture-model"},
        raw_response={
            "id": f"response-{sequence}",
            "model": "fixture-model",
            "usage": raw_usage,
        },
        final_response=None,
    )
    return _record(
        sequence,
        provider="anthropic",
        usage=evidence.usage,
        pricing_context=evidence.pricing_context,
        direct_cost=evidence.direct_cost,
        provider_extensions=evidence.provider_extensions,
        response_model=evidence.response_model,
        provider_response_id=evidence.provider_response_id,
        **overrides,
    )


def _openrouter_record(
    sequence: int, raw_usage: dict[str, Any] | None, **overrides: Any
) -> ProviderAttemptRecord:
    raw_response = (
        {
            "id": f"response-{sequence}",
            "model": "fixture-model",
            "usage": raw_usage,
        }
        if raw_usage is not None
        else None
    )
    evidence = normalize_openrouter_usage_accounting(
        request_body={"model": "openrouter/fixture-model"},
        raw_response=raw_response,
        final_response=None,
        failed=overrides.get("outcome", "succeeded") != "succeeded",
    )
    return _record(
        sequence,
        usage=evidence.usage,
        pricing_context=evidence.pricing_context,
        direct_cost=evidence.direct_cost,
        provider_extensions=evidence.provider_extensions,
        response_model=evidence.response_model,
        provider_response_id=evidence.provider_response_id,
        **overrides,
    )


def _reference(value: CacheReference | None) -> CacheReference:
    assert value is not None
    return value


def _render(
    records: tuple[ProviderAttemptRecord, ...] = (),
    *,
    supported: bool = True,
    cache_status: str = "miss",
    capture_status: str = "complete",
    cache_reference: CacheReference | None = None,
) -> dict[str, Any]:
    collector: Any = _Collector(records, status=capture_status) if supported else None
    return render_aigw_metadata(
        collector=collector,
        supported=supported,
        cache_status=cache_status,  # type: ignore[arg-type]
        gateway_call_id=_CALL_ID,
        cache_reference=cache_reference,
    )


def _release_fixtures() -> dict[str, dict[str, Any]]:
    transport_failure = _openrouter_record(
        1,
        None,
        outcome="transport_error",
        http_status=None,
        latency_ms=None,
        failure_code="transport_connect_error",
    )
    openrouter_full_usage = {
        "prompt_tokens": 56,
        "completion_tokens": 41,
        "prompt_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 6},
        "completion_tokens_details": {"reasoning_tokens": 8},
        "cost": "0.001",
        "cost_details": {"upstream_inference_cost": "0.0008"},
    }
    retry_success = _openrouter_record(2, openrouter_full_usage, attempt_index=2)
    anthropic_full = _anthropic_record(
        1,
        {
            "input_tokens": 100,
            "output_tokens": 25,
            "cache_read_input_tokens": 20,
            "cache_creation_input_tokens": 10,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 7,
                "ephemeral_1h_input_tokens": 3,
            },
            "output_tokens_details": {"thinking_tokens": 7},
            "service_tier": "standard",
        },
    )
    cache_reference = _reference(
        openrouter_cache_reference_from_cached(
            {"usage": {"prompt_tokens": 2, "completion_tokens": 1, "cost": "0.001"}}
        )
    )
    anthropic_cache_reference = _reference(
        anthropic_cache_reference_from_cached(
            {
                "usage": {
                    "prompt_tokens": 130,
                    "completion_tokens": 25,
                    "prompt_tokens_details": {
                        "text_tokens": 100,
                        "cached_tokens": 20,
                        "cache_creation_tokens": 10,
                        "cache_creation_token_details": {
                            "ephemeral_5m_input_tokens": 7,
                            "ephemeral_1h_input_tokens": 3,
                        },
                    },
                }
            }
        )
    )
    fixtures = {
        "openrouter_full_success": _render((_openrouter_record(1, openrouter_full_usage),)),
        "openrouter_explicit_zero": _render(
            (
                _openrouter_record(
                    1,
                    {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                        "cost": 0,
                    },
                ),
            )
        ),
        "openrouter_missing_evidence": _render((_openrouter_record(1, {}),)),
        "openrouter_retry": _render((transport_failure, retry_success)),
        "openrouter_failure_with_usage": _render(
            (
                _openrouter_record(
                    1,
                    {"prompt_tokens": 2, "cost": "0.001"},
                    outcome="provider_error",
                    http_status=429,
                    failure_code="provider_status_error",
                ),
            )
        ),
        "anthropic_full_cache_ttl_success": _render((anthropic_full,)),
        "anthropic_missing_cache_evidence": _render(
            (
                _anthropic_record(
                    1,
                    {"input_tokens": 2, "output_tokens": 1},
                ),
            )
        ),
        "anthropic_service_tier_tool_usage": _render(
            (
                _anthropic_record(
                    1,
                    {
                        "input_tokens": 2,
                        "output_tokens": 1,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "service_tier": "priority",
                        "server_tool_use": {"web_search_requests": 1},
                    },
                ),
            )
        ),
        "anthropic_cache_replay": _render(
            cache_status="hit",
            cache_reference=anthropic_cache_reference,
        ),
        "hidden_transport_resend": _render((transport_failure, retry_success)),
        "gateway_overload_retry": _render(
            (
                _openrouter_record(
                    1,
                    {},
                    outcome="provider_error",
                    http_status=529,
                    failure_code="provider_status_error",
                ),
                _openrouter_record(
                    2,
                    openrouter_full_usage,
                    dispatch_index=2,
                    attempt_index=1,
                ),
            )
        ),
        "response_less_transport_failure": _render((transport_failure,)),
        "conversion_failure": _render(
            (
                _openrouter_record(
                    1,
                    openrouter_full_usage,
                    outcome="conversion_error",
                    failure_code="response_conversion_failed",
                ),
            )
        ),
        "unsupported_provider_miss": _render(supported=False),
        "cache_hit_reference": _render(
            cache_status="hit",
            cache_reference=cache_reference,
        ),
        "bounds_overflow": _render(tuple(_record(index) for index in range(1, 66))),
        "huggingface_pinned_backend": _render(
            (
                _record(
                    1,
                    provider="huggingface",
                    pricing_context=PricingContext(backend="hf-inference-endpoint"),
                    direct_cost=DirectCost.unavailable(),
                ),
            )
        ),
        "huggingface_unpinned_backend": _render(
            (
                _record(
                    1,
                    provider="huggingface",
                    pricing_context=PricingContext(backend=None),
                    direct_cost=DirectCost.unavailable(),
                ),
            )
        ),
    }
    return fixtures


@pytest.fixture(scope="module")
def release_fixtures() -> dict[str, dict[str, Any]]:
    return _release_fixtures()


def test_release_fixture_matrix_is_complete(
    release_fixtures: dict[str, dict[str, Any]],
) -> None:
    assert set(release_fixtures) == _REQUIRED_METADATA_FIXTURES
    assert _ROUTE_ONLY_ACCEPTANCE == {
        "non_negotiated_response_parity",
        "unknown_accounting_version_rejection",
    }


def test_release_fixture_canonical_json_is_immutable(
    release_fixtures: dict[str, dict[str, Any]],
) -> None:
    actual = {
        name: sha256(
            json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()
        for name, metadata in release_fixtures.items()
    }
    assert actual == _EXPECTED_FIXTURE_SHA256


def test_every_release_fixture_uses_schema_valid_exact_ids_and_wire_shape(
    release_fixtures: dict[str, dict[str, Any]],
) -> None:
    validator = Draft202012Validator(_schema())
    for name, metadata in release_fixtures.items():
        errors = sorted(validator.iter_errors(metadata), key=lambda error: list(error.path))
        assert errors == [], f"{name}: {[error.message for error in errors]}"
        assert metadata["usage_accounting"]["gateway_call_id"] == _CALL_ID
        for attempt in metadata["usage_accounting"]["attempts"]:
            assert len(attempt["attempt_id"]) == len("attempt_") + 32


def test_release_fixtures_pin_retry_failure_cache_and_bound_semantics(
    release_fixtures: dict[str, dict[str, Any]],
) -> None:
    hidden = release_fixtures["hidden_transport_resend"]["usage_accounting"]["attempts"]
    overload = release_fixtures["gateway_overload_retry"]["usage_accounting"]["attempts"]
    assert [(row["dispatch_index"], row["attempt_index"]) for row in hidden] == [(1, 1), (1, 2)]
    assert [(row["dispatch_index"], row["attempt_index"]) for row in overload] == [(1, 1), (2, 1)]

    response_less = release_fixtures["response_less_transport_failure"]["usage_accounting"]
    assert response_less["attempts"][0]["http_status"] is None
    assert response_less["attempts"][0]["latency_ms"] is None
    assert response_less["attempts"][0]["outcome"] == "transport_error"
    assert response_less["attempts"][0]["response_model"] is None
    assert response_less["attempts"][0]["provider_response_id"] is None

    cache_hit = release_fixtures["cache_hit_reference"]
    assert cache_hit["usage_accounting"]["attempts"] == []
    assert (
        cache_hit["usage_accounting"]["cache"]["reference"]["incurred_in_current_request"] is False
    )
    assert cache_hit["request_economics"]["observed_new_attempts"] == 0

    overflow = release_fixtures["bounds_overflow"]
    assert overflow["usage_accounting"]["observed_attempts"] == 65
    assert overflow["usage_accounting"]["rendered_attempts"] == 64
    assert overflow["usage_accounting"]["omitted_attempts"] == 1
    assert overflow["usage_accounting"]["capture_status"] == "partial"
    assert overflow["request_economics"]["known_direct_cost_subtotals"] == []

    missing_cache = release_fixtures["anthropic_missing_cache_evidence"]["usage_accounting"][
        "attempts"
    ][0]
    assert missing_cache["usage"]["status"] == "partial"
    assert missing_cache["usage"]["input"] == {
        "total": None,
        "uncached": 2,
        "cache_read": None,
        "cache_write": None,
        "cache_write_by_ttl": [],
    }

    tool_attempt = release_fixtures["anthropic_service_tier_tool_usage"]["usage_accounting"][
        "attempts"
    ][0]
    assert tool_attempt["usage"]["input"]["total"] == 2
    assert tool_attempt["pricing_context"]["service_tier"] == "priority"
    assert tool_attempt["provider_extensions"] == [
        {
            "namespace": "anthropic.usage.v1",
            "facts": [
                {
                    "name": "web_search_requests",
                    "kind": "integer",
                    "value": 1,
                    "unit": "requests",
                    "source": "anthropic.usage.server_tool_use.web_search_requests",
                }
            ],
            "truncated": False,
        }
    ]


def test_release_fixture_rejects_raw_provider_text_and_nested_objects(
    release_fixtures: dict[str, dict[str, Any]],
) -> None:
    clean = release_fixtures["openrouter_full_success"]
    assert "PRIVATE PROMPT" not in json.dumps(clean)

    leaked = deepcopy(clean)
    leaked["usage_accounting"]["attempts"][0]["provider_native_body"] = {"prompt": "PRIVATE PROMPT"}
    with pytest.raises(ValidationError):
        Draft202012Validator(_schema()).validate(leaked)


def test_huggingface_fixtures_prove_canonical_fit_without_claiming_support(
    release_fixtures: dict[str, dict[str, Any]],
) -> None:
    pinned = release_fixtures["huggingface_pinned_backend"]["usage_accounting"]["attempts"][0]
    unpinned = release_fixtures["huggingface_unpinned_backend"]["usage_accounting"]["attempts"][0]
    assert pinned["pricing_context"]["backend"] == "hf-inference-endpoint"
    assert unpinned["pricing_context"]["backend"] is None
    assert HuggingFaceProviderPlugin().usage_accounting_strategy().is_supported is False


def test_release_fixture_exercises_private_input_without_publishing_it() -> None:
    sentinel = "PRIVATE PROMPT"
    request_body = {
        "model": "openrouter/fixture-model",
        "messages": [{"role": "user", "content": sentinel}],
    }
    raw_response = {
        "id": "response-1",
        "model": "fixture-model",
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "cost": "0.001"},
        "provider_debug": {"prompt": sentinel},
    }
    evidence = normalize_openrouter_usage_accounting(
        request_body=request_body,
        raw_response=raw_response,
        final_response=None,
    )
    fixture = _render(
        (
            _record(
                1,
                usage=evidence.usage,
                pricing_context=evidence.pricing_context,
                direct_cost=evidence.direct_cost,
                provider_extensions=evidence.provider_extensions,
                response_model=evidence.response_model,
                provider_response_id=evidence.provider_response_id,
            ),
        )
    )

    assert sentinel in json.dumps({"request": request_body, "response": raw_response})
    assert sentinel not in json.dumps(fixture)
    Draft202012Validator(_schema()).validate(fixture)
    canonical = json.dumps(fixture, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert (
        sha256(canonical.encode()).hexdigest()
        == "10037cb637daefbfc7322723a7fa3f399fd7fd85d0251e536b6ee05f34019ef9"
    )
