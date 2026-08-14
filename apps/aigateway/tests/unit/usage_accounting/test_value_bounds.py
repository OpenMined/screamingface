"""Adversarial bounds for values that cross the AIGateway/Engine boundary."""

from __future__ import annotations

from typing import Any

import pytest

from aigateway.plugins.taxonomy import (
    CacheReference,
    CacheWriteTTL,
    DirectCost,
    InputTokenUsage,
    PricingContext,
    ProviderExtension,
    ProviderExtensionFact,
    ProviderUsageAccountingEvidence,
    TokenUsage,
    UsageAccountingStrategy,
)
from aigateway.plugins.taxonomy.collector import RequestAccountingCollector
from aigateway.plugins.taxonomy.render import render_aigw_metadata


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


def test_money_and_decimal_extensions_accept_33_but_not_34_fractional_digits() -> None:
    accepted = "0.123456789012345678901234567890123"
    rejected = accepted + "4"

    assert (
        DirectCost.reported(amount=accepted, unit="credits", source="provider.cost").amount
        == accepted
    )
    assert (
        ProviderExtensionFact(
            name="cost_detail",
            kind="decimal",
            value=accepted,
            unit=None,
            source="provider.cost_detail",
        ).value
        == accepted
    )
    with pytest.raises(ValueError):
        DirectCost.reported(amount=rejected, unit="credits", source="provider.cost")
    with pytest.raises(ValueError):
        ProviderExtensionFact(
            name="cost_detail",
            kind="decimal",
            value=rejected,
            unit=None,
            source="provider.cost_detail",
        )


def test_unit_unknown_direct_cost_cannot_claim_a_known_unit() -> None:
    with pytest.raises(ValueError):
        DirectCost(status="unit_unknown", amount="1", unit="usd", source="provider.cost")


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
        ProviderExtension(namespace="anthropic.\N{SNOWMAN}")


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
        ProviderExtension(namespace="provider", facts=(fact,) * 9)


def test_extension_fact_count_is_bounded_across_namespaces() -> None:
    fact = ProviderExtensionFact(
        name="count", kind="integer", value=1, unit="events", source="provider.count"
    )
    first = ProviderExtension(namespace="provider.a", facts=(fact,) * 5)
    second = ProviderExtension(namespace="provider.b", facts=(fact,) * 4)
    with pytest.raises(ValueError):
        ProviderUsageAccountingEvidence(provider_extensions=(first, second))


def test_nested_mapper_value_objects_are_runtime_validated() -> None:
    with pytest.raises(ValueError):
        TokenUsage(status="bogus")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        TokenUsage(input=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        TokenUsage(output=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        InputTokenUsage(cache_write_by_ttl=(object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProviderUsageAccountingEvidence(usage=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CacheReference(usage=object())  # type: ignore[arg-type]


def test_extension_containers_and_flags_are_runtime_validated() -> None:
    with pytest.raises(ValueError):
        ProviderExtension(namespace="provider", facts=(object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProviderExtension(namespace="provider", truncated="yes")  # type: ignore[arg-type]


def test_strategy_capability_is_runtime_validated() -> None:
    with pytest.raises(ValueError):
        UsageAccountingStrategy(capability="unknown")  # type: ignore[arg-type]


def test_canonical_scalars_reject_string_subclasses() -> None:
    class _SpoofedASCII(str):
        def encode(self, *_args: Any, **_kwargs: Any) -> bytes:
            return b"safe"

    class _SpoofedEnum(str):
        def __hash__(self) -> int:
            return hash("complete")

        def __eq__(self, _other: object) -> bool:
            return True

    class _SpoofedDecimal(str):
        def endswith(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

    with pytest.raises(ValueError):
        PricingContext(backend=_SpoofedASCII("line\nbreak"))
    with pytest.raises(ValueError):
        TokenUsage(status=_SpoofedEnum("not-a-status"))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        UsageAccountingStrategy(capability=_SpoofedEnum("not-a-capability"))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CacheReference(kind=_SpoofedEnum("not-a-kind"))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        DirectCost.reported(
            amount=_SpoofedDecimal("1.0"),
            unit="credits",
            source="provider.cost",
        )


def test_pricing_context_refuses_unbounded_provider_text() -> None:
    with pytest.raises(ValueError):
        PricingContext(backend="x" * 65)


def test_pricing_context_refuses_noncanonical_service_tier() -> None:
    with pytest.raises(ValueError):
        PricingContext(service_tier="provider-new-value")  # type: ignore[arg-type]


@pytest.mark.parametrize("backend", ["line\nbreak", "nul\x00byte", "delete\x7fbyte"])
def test_pricing_context_matches_the_schema_printable_ascii_domain(backend: str) -> None:
    with pytest.raises(ValueError):
        PricingContext(backend=backend)


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
        provider="openrouter", requested_model="openrouter/x/y", transport="litellm_async_http"
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
        provider="anthropic", requested_model=requested_model, transport="litellm_async_http"
    )
    collector.begin_dispatch()
    marker = object()
    collector.on_send_admitted(marker)
    collector.on_response_completed(marker, status=200, raw_evidence={})
    assert collector.records()[0].requested_model is None


def test_unencodable_requested_model_is_omitted_without_breaking_rendering() -> None:
    collector = RequestAccountingCollector(
        provider="anthropic",
        requested_model="anthropic/claude\ud800",
        transport="litellm_async_http",
    )
    collector.begin_dispatch()
    marker = object()
    collector.on_send_admitted(marker)
    collector.on_response_completed(marker, status=200, raw_evidence={})

    metadata = render_aigw_metadata(
        collector=collector,
        supported=True,
        cache_status="miss",
        gateway_call_id=collector.gateway_call_id,
    )

    assert metadata["usage_accounting"]["attempts"][0]["requested_model"] is None


def test_malformed_mapper_identifier_is_omitted_without_breaking_rendering() -> None:
    collector = RequestAccountingCollector(
        provider="anthropic",
        requested_model="anthropic/claude",
        transport="litellm_async_http",
    )
    collector.begin_dispatch()
    marker = object()
    collector.on_send_admitted(marker)
    collector.on_response_completed(marker, status=200, raw_evidence={})
    attempt_id = collector.open_records()[0][0]
    collector.apply_evidence(
        attempt_id,
        ProviderUsageAccountingEvidence(
            supported=True,
            response_model=123,  # type: ignore[arg-type]
        ),
    )

    metadata = render_aigw_metadata(
        collector=collector,
        supported=True,
        cache_status="miss",
        gateway_call_id=collector.gateway_call_id,
    )

    assert metadata["usage_accounting"]["attempts"][0]["response_model"] is None


def test_safe_string_subclass_is_normalized_without_calling_its_encode_override() -> None:
    class _HostileString(str):
        def __bool__(self) -> bool:
            raise RuntimeError("subclass truthiness override must not run")

        def encode(self, *_args: Any, **_kwargs: Any) -> bytes:
            raise RuntimeError("subclass override must not run")

    collector = RequestAccountingCollector(
        provider="anthropic",
        requested_model="anthropic/claude",
        transport="litellm_async_http",
    )
    collector.begin_dispatch()
    marker = object()
    collector.on_send_admitted(marker)
    collector.on_response_completed(marker, status=200, raw_evidence={})
    collector.apply_evidence(
        collector.open_records()[0][0],
        ProviderUsageAccountingEvidence(
            supported=True,
            response_model=_HostileString("claude-safe"),
        ),
    )

    metadata = render_aigw_metadata(
        collector=collector,
        supported=True,
        cache_status="miss",
        gateway_call_id=collector.gateway_call_id,
    )

    response_model = metadata["usage_accounting"]["attempts"][0]["response_model"]
    assert response_model == "claude-safe"
    assert type(response_model) is str


@pytest.mark.parametrize(
    ("kind", "value"),
    [("integer", "1"), ("integer", True), ("decimal", 1), ("decimal", True)],
)
def test_extension_fact_kind_rejects_mismatched_scalar_types(kind: str, value: Any) -> None:
    with pytest.raises(ValueError):
        ProviderExtensionFact(
            name="value",
            kind=kind,  # type: ignore[arg-type]
            value=value,
            unit=None,
            source="provider.value",
        )
