"""Adversarial bounds for values that cross the AIGateway/Engine boundary."""

from __future__ import annotations

from typing import Any

import pytest

from aigateway.core.usage_accounting import (
    CacheReference,
    CacheWriteTTL,
    DirectCost,
    InputTokenUsage,
    PricingContext,
    ProviderExtension,
    ProviderExtensionFact,
    ProviderUsageAccountingEvidence,
)
from aigateway.core.usage_accounting._collector import RequestAccountingCollector


@pytest.mark.parametrize("amount", ["-1", "1e3", "01", "1.0", "0.00", "NaN"])
def test_direct_cost_requires_one_bounded_canonical_spelling(amount: str) -> None:
    with pytest.raises(ValueError):
        DirectCost.reported(amount=amount, unit="credits", source="provider.cost")


def test_reported_direct_cost_requires_unit_and_source() -> None:
    with pytest.raises(ValueError):
        DirectCost(status="reported", amount="1")


def test_nonreported_direct_cost_cannot_smuggle_amount_metadata() -> None:
    with pytest.raises(ValueError):
        DirectCost(status="unavailable", amount="1", unit="credits", source="x")


@pytest.mark.parametrize("count", [-1, 2**53, True])
def test_token_counts_outside_json_safe_nonnegative_range_are_rejected(count: Any) -> None:
    with pytest.raises(ValueError):
        InputTokenUsage(total=count)


def test_cache_ttl_breakdown_is_bounded() -> None:
    row = CacheWriteTTL(ttl_seconds=300, tokens=1)
    with pytest.raises(ValueError):
        InputTokenUsage(cache_write_by_ttl=(row,) * 9)


def test_extension_namespace_is_bounded_ascii() -> None:
    with pytest.raises(ValueError):
        ProviderExtension(namespace="anthropic.\N{SNOWMAN}.v1")


def test_extension_fact_refuses_nested_provider_objects() -> None:
    with pytest.raises(ValueError):
        ProviderExtensionFact(
            name="raw",
            kind="enum",
            value={"prompt": "must-not-cross"},  # type: ignore[arg-type]
            unit=None,
            source="provider.raw",
        )


def test_unknown_extension_kind_cannot_bypass_scalar_validation() -> None:
    with pytest.raises(ValueError):
        ProviderExtensionFact(
            name="raw",
            kind="provider_object",  # type: ignore[arg-type]
            value={"prompt": "must-not-cross"},  # type: ignore[arg-type]
            unit=None,
            source="provider.raw",
        )


def test_extension_fact_count_is_bounded() -> None:
    fact = ProviderExtensionFact(
        name="count", kind="integer", value=1, unit="events", source="provider.count"
    )
    with pytest.raises(ValueError):
        ProviderExtension(namespace="provider.v1", facts=(fact,) * 9)


def test_extension_fact_count_is_bounded_across_namespaces() -> None:
    fact = ProviderExtensionFact(
        name="count", kind="integer", value=1, unit="events", source="provider.count"
    )
    first = ProviderExtension(namespace="provider.a.v1", facts=(fact,) * 5)
    second = ProviderExtension(namespace="provider.b.v1", facts=(fact,) * 4)
    with pytest.raises(ValueError):
        ProviderUsageAccountingEvidence(provider_extensions=(first, second))


def test_pricing_context_refuses_unbounded_provider_text() -> None:
    with pytest.raises(ValueError):
        PricingContext(backend="x" * 65)


def test_pricing_context_refuses_noncanonical_service_tier() -> None:
    with pytest.raises(ValueError):
        PricingContext(service_tier="provider-new-value")  # type: ignore[arg-type]


def test_provider_mapper_cannot_author_a_public_failure_code() -> None:
    with pytest.raises(TypeError):
        ProviderUsageAccountingEvidence(
            failure_code="Bearer sk-provider-secret"  # type: ignore[call-arg]
        )


def test_cache_reference_can_never_claim_current_request_spend() -> None:
    with pytest.raises(ValueError):
        CacheReference(incurred_in_current_request=True)  # type: ignore[arg-type]


def test_cache_reference_coverage_cannot_be_widened_by_a_mapper() -> None:
    with pytest.raises(ValueError):
        CacheReference(coverage="whole_original_request")  # type: ignore[arg-type]


def test_overlong_provider_response_id_is_omitted_not_truncated() -> None:
    collector = RequestAccountingCollector(
        provider="openrouter", requested_model="openrouter/x/y", transport="litellm_async_http_v1"
    )
    collector.begin_dispatch()
    marker = object()
    collector.on_send_admitted(marker)
    collector.on_response_completed(marker, status=200, raw_evidence={})
    attempt_id = collector.open_records()[0][0]
    provider_id = "x" * 257
    collector.apply_evidence(
        attempt_id,
        ProviderUsageAccountingEvidence(supported=True, provider_response_id=provider_id),
    )
    assert collector.records()[0].provider_response_id is None
    assert provider_id not in str(collector.records()[0].as_json())


def test_overlong_model_is_omitted_not_aliased_by_truncation() -> None:
    requested_model = "m" * 513
    collector = RequestAccountingCollector(
        provider="anthropic", requested_model=requested_model, transport="litellm_async_http_v1"
    )
    collector.begin_dispatch()
    marker = object()
    collector.on_send_admitted(marker)
    collector.on_response_completed(marker, status=200, raw_evidence={})
    assert collector.records()[0].requested_model is None
