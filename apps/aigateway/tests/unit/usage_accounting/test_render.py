"""The bounded ``_aigw`` renderer is the only public wire-shape authority."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from aigateway.core.usage_accounting import (
    CacheReference,
    DirectCost,
    ProviderAttemptRecord,
    ProviderExtension,
    ProviderExtensionFact,
    RequestAccountingCollector,
    TokenUsage,
)
from aigateway.core.usage_accounting._render import (
    MAX_METADATA_BYTES,
    METADATA_KEY,
    attach_metadata,
    merged_error_detail,
    render_aigw_metadata,
)


def _record(**overrides: Any) -> ProviderAttemptRecord:
    base: dict[str, Any] = {
        "attempt_id": "attempt_1",
        "sequence": 1,
        "dispatch_index": 1,
        "attempt_index": 1,
        "provider": "openrouter",
        "transport": "litellm_async_http",
        "outcome": "succeeded",
    }
    base.update(overrides)
    return ProviderAttemptRecord(**base)


class _FakeCollector:
    def __init__(
        self,
        records: tuple[ProviderAttemptRecord, ...] = (),
        *,
        status: str = "complete",
    ) -> None:
        self._records = records
        self._status = status

    def records(self) -> tuple[ProviderAttemptRecord, ...]:
        return self._records

    def status(self) -> Any:
        return self._status


def _render(collector: Any = None, **kwargs: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "collector": collector,
        "supported": True,
        "cache_status": "miss",
        "gateway_call_id": "call_test",
    }
    params.update(kwargs)
    return render_aigw_metadata(**params)


class TestWireShape:
    def test_exactly_two_siblings_under_one_namespace(self) -> None:
        assert set(_render()) == {"usage_accounting", "request_economics"}

    def test_attempt_declares_schema_and_response_identity(self) -> None:
        metadata = _render(_FakeCollector((_record(provider_response_id="gen-1"),)))
        attempt = metadata["usage_accounting"]["attempts"][0]
        assert attempt["schema"] == "aigw.provider_attempt"
        assert attempt["attempt_id"] == "attempt_1"
        assert attempt["provider_response_id"] == "gen-1"
        assert "provider_call_id" not in attempt
        assert "evidence_complete" not in attempt

    def test_gateway_call_id_is_carried_verbatim(self) -> None:
        metadata = _render(gateway_call_id="call_abc123")
        assert metadata["usage_accounting"]["gateway_call_id"] == "call_abc123"


class TestDirectCostSummary:
    def test_same_unit_and_source_are_summed_with_decimal(self) -> None:
        collector = _FakeCollector(
            (
                _record(
                    direct_cost=DirectCost.reported(
                        amount="0.1", unit="openrouter_credits", source="s"
                    )
                ),
                _record(
                    attempt_id="attempt_2",
                    direct_cost=DirectCost.reported(
                        amount="0.2", unit="openrouter_credits", source="s"
                    ),
                ),
            )
        )
        economics = _render(collector)["request_economics"]
        assert economics["known_direct_cost_subtotals"] == [
            {"amount": "0.3", "unit": "openrouter_credits", "source": "s"}
        ]
        assert economics["direct_cost_status"] == "complete"

    def test_different_units_or_sources_are_never_merged(self) -> None:
        collector = _FakeCollector(
            (
                _record(direct_cost=DirectCost.reported(amount="1", unit="credits", source="a")),
                _record(
                    attempt_id="attempt_2",
                    direct_cost=DirectCost.reported(amount="2", unit="usd", source="a"),
                ),
                _record(
                    attempt_id="attempt_3",
                    direct_cost=DirectCost.reported(amount="3", unit="credits", source="b"),
                ),
            )
        )
        summary = _render(collector)["request_economics"]["known_direct_cost_subtotals"]
        assert {(entry["unit"], entry["source"]) for entry in summary} == {
            ("credits", "a"),
            ("credits", "b"),
            ("usd", "a"),
        }

    def test_missing_direct_cost_yields_partial_known_subtotal(self) -> None:
        collector = _FakeCollector(
            (
                _record(direct_cost=DirectCost.reported(amount="1", unit="credits", source="s")),
                _record(attempt_id="attempt_2", direct_cost=DirectCost.unavailable()),
            )
        )
        economics = _render(collector)["request_economics"]
        assert economics["direct_cost_status"] == "partial"
        assert economics["known_direct_cost_subtotals"] == [
            {"amount": "1", "unit": "credits", "source": "s"}
        ]

    def test_subtotal_overflow_degrades_instead_of_violating_schema(self) -> None:
        cost = DirectCost.reported(amount="999999999999999999", unit="credits", source="s")
        collector = _FakeCollector(
            (_record(direct_cost=cost), _record(attempt_id="attempt_2", direct_cost=cost))
        )
        economics = _render(collector)["request_economics"]
        assert economics["direct_cost_status"] == "partial"
        assert economics["known_direct_cost_subtotals"] == []

    def test_valid_high_precision_subtotal_is_exact_and_complete(self) -> None:
        first = DirectCost.reported(
            amount="999999999999999999.000000000000000001",
            unit="credits",
            source="s",
        )
        second = DirectCost.reported(amount="0.000000000000000001", unit="credits", source="s")
        economics = _render(
            _FakeCollector(
                (
                    _record(direct_cost=first),
                    _record(attempt_id="attempt_2", direct_cost=second),
                )
            )
        )["request_economics"]
        assert economics["direct_cost_status"] == "complete"
        assert economics["known_direct_cost_subtotals"] == [
            {
                "amount": "999999999999999999.000000000000000002",
                "unit": "credits",
                "source": "s",
            }
        ]

    @pytest.mark.parametrize("status", ["absent", "unavailable", "invalid", "unit_unknown"])
    def test_nonaggregable_cost_never_contributes(self, status: str) -> None:
        if status == "absent":
            cost = DirectCost.absent()
        elif status == "unavailable":
            cost = DirectCost.unavailable()
        elif status == "invalid":
            cost = DirectCost.invalid()
        else:
            cost = DirectCost.unit_unknown(amount="1", source="s")
        economics = _render(_FakeCollector((_record(direct_cost=cost),)))["request_economics"]
        assert economics["known_direct_cost_subtotals"] == []
        assert economics["direct_cost_status"] == "unavailable"


class TestCaptureAndCostStatuses:
    def test_unsupported_provider_is_not_zero_or_complete(self) -> None:
        metadata = _render(supported=False)
        assert metadata["usage_accounting"]["capture_status"] == "accounting_not_supported"
        assert metadata["request_economics"]["direct_cost_status"] == "not_applicable"

    def test_dispatched_without_an_observed_attempt_has_no_applicable_attempt_cost(self) -> None:
        collector = _FakeCollector(status="partial")
        metadata = _render(collector)
        assert metadata["usage_accounting"]["observed_attempts"] == 0
        assert metadata["request_economics"]["direct_cost_status"] == "not_applicable"

    def test_cache_hit_is_not_applicable(self) -> None:
        metadata = _render(cache_status="hit")
        assert metadata["usage_accounting"]["capture_status"] == "not_applicable"
        assert metadata["request_economics"]["direct_cost_status"] == "not_applicable"

    def test_no_observed_attempt_is_not_applicable(self) -> None:
        metadata = _render()
        assert metadata["request_economics"]["direct_cost_status"] == "not_applicable"

    def test_partial_capture_suppresses_unverifiable_subtotal(self) -> None:
        collector = _FakeCollector(
            (_record(direct_cost=DirectCost.reported(amount="1", unit="credits", source="s")),),
            status="partial",
        )
        economics = _render(collector)["request_economics"]
        assert economics["direct_cost_status"] == "partial"
        assert economics["known_direct_cost_subtotals"] == []


class TestCacheReference:
    def test_hit_renders_limited_historical_reference_not_avoided_cost(self) -> None:
        reference = CacheReference(
            usage=TokenUsage(status="partial", source="cached_converted_response"),
            direct_cost=DirectCost.reported(
                amount="0.0012",
                unit="openrouter_credits",
                source="cached_response.usage.cost",
            ),
        )
        metadata = _render(cache_status="hit", cache_reference=reference)
        rendered = metadata["usage_accounting"]["cache"]["reference"]
        assert rendered["coverage"] == "final_successful_response_only"
        assert rendered["incurred_in_current_request"] is False
        assert "avoided_cost" not in str(metadata)
        assert metadata["usage_accounting"]["attempts"] == []

    def test_reference_is_suppressed_on_miss(self) -> None:
        metadata = _render(cache_reference=CacheReference())
        assert metadata["usage_accounting"]["cache"]["reference"] is None


class TestBounds:
    def test_renderer_is_total_and_schema_valid_across_generated_boundary_records(self) -> None:
        schema = json.loads(
            files("aigateway.core.usage_accounting")
            .joinpath("usage_accounting.schema.json")
            .read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        record_counts = (0, 1, 63, 64, 65)
        model_lengths = (0, 1, 512)

        for case in range(90):
            amount = f"{case % 10}.123456789012345678901234567890123"
            extension = ProviderExtension(
                namespace="provider.audit",
                facts=(
                    ProviderExtensionFact(
                        name="cost_detail",
                        kind="decimal",
                        value=amount,
                        unit=None,
                        source="provider.usage.cost_detail",
                    ),
                ),
            )
            model_length = model_lengths[case % len(model_lengths)]
            records = tuple(
                _record(
                    attempt_id=f"attempt_{index:032x}",
                    sequence=index,
                    requested_model=("m" * model_length) or None,
                    response_model=("r" * model_length) or None,
                    provider_response_id=f"provider-{index}",
                    direct_cost=DirectCost.reported(
                        amount=amount,
                        unit="openrouter_credits",
                        source="openrouter.usage.cost",
                    ),
                    provider_extensions=(extension,),
                )
                for index in range(1, record_counts[case % len(record_counts)] + 1)
            )

            metadata = _render(
                _FakeCollector(records, status="partial" if case % 2 else "complete"),
                gateway_call_id=f"call_{case:032x}",
            )

            errors = list(validator.iter_errors(metadata))
            assert not errors, f"generated case {case}: {errors}"
            assert (
                len(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode())
                <= MAX_METADATA_BYTES
            )

    def test_more_than_64_attempts_are_counted_then_omitted(self) -> None:
        records = tuple(
            _record(attempt_id=f"attempt_{index}", sequence=index) for index in range(1, 66)
        )
        metadata = _render(_FakeCollector(records))
        accounting = metadata["usage_accounting"]
        assert accounting["observed_attempts"] == 65
        assert accounting["rendered_attempts"] == 64
        assert accounting["omitted_attempts"] == 1
        assert accounting["capture_status"] == "partial"
        assert metadata["request_economics"]["known_direct_cost_subtotals"] == []

    def test_large_extension_input_is_globally_capped_without_dropping_attempts(self) -> None:
        fact = ProviderExtensionFact(
            name="n" * 64,
            kind="enum",
            value="v" * 64,
            unit=None,
            source="s" * 128,
        )
        extension = ProviderExtension(namespace="x", facts=(fact,) * 8)
        records = tuple(
            _record(
                attempt_id=f"attempt_{index}",
                sequence=index,
                provider_extensions=(extension,),
            )
            for index in range(1, 65)
        )
        metadata = _render(_FakeCollector(records))
        encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode()
        assert len(encoded) <= MAX_METADATA_BYTES
        assert metadata["usage_accounting"]["rendered_attempts"] == 64
        attempts = metadata["usage_accounting"]["attempts"]
        assert (
            sum(
                len(namespace["facts"])
                for attempt in attempts
                for namespace in attempt["provider_extensions"]
            )
            == 32
        )
        assert any(attempt["provider_extensions_truncated"] for attempt in attempts)

    def test_metadata_size_pressure_drops_attempts_and_suppresses_subtotals(self) -> None:
        records = tuple(
            _record(
                attempt_id=f"attempt_{index}",
                sequence=index,
                requested_model="m" * 512,
                response_model="r" * 512,
                provider_response_id="i" * 256,
                direct_cost=DirectCost.reported(
                    amount="1", unit="openrouter_credits", source="openrouter.usage.cost"
                ),
            )
            for index in range(1, 65)
        )
        metadata = _render(_FakeCollector(records))
        encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode()
        assert len(encoded) <= MAX_METADATA_BYTES
        accounting = metadata["usage_accounting"]
        assert accounting["rendered_attempts"] < 64
        assert accounting["omitted_attempts"] > 0
        assert accounting["capture_status"] == "partial"
        economics = metadata["request_economics"]
        assert economics["direct_cost_status"] == "partial"
        assert economics["known_direct_cost_subtotals"] == []

    def test_extension_facts_are_capped_across_the_response(self) -> None:
        fact = ProviderExtensionFact(
            name="events", kind="integer", value=1, unit="events", source="provider.events"
        )
        extension = ProviderExtension(namespace="provider", facts=(fact,) * 8)
        records = tuple(
            _record(
                attempt_id=f"attempt_{index}",
                sequence=index,
                provider_extensions=(extension,),
            )
            for index in range(1, 6)
        )
        attempts = _render(_FakeCollector(records))["usage_accounting"]["attempts"]
        assert (
            sum(
                len(namespace["facts"])
                for attempt in attempts
                for namespace in attempt["provider_extensions"]
            )
            == 32
        )
        assert attempts[-1]["provider_extensions"] == []
        assert attempts[-1]["provider_extensions_truncated"] is True


class TestAttachAndErrors:
    def test_original_payload_is_never_mutated(self) -> None:
        payload = {"id": "msg_1", "choices": []}
        result = attach_metadata(payload, {"usage_accounting": {}})
        assert METADATA_KEY not in payload
        assert METADATA_KEY in result
        assert result is not payload

    def test_provider_payload_is_carried_through_unchanged(self) -> None:
        payload = {"id": "msg_1", "model": "m", "choices": [{"x": 1}]}
        result = attach_metadata(payload, {})
        assert {key: value for key, value in result.items() if key != METADATA_KEY} == payload

    def test_aigw_sits_beside_detail_not_inside_it(self) -> None:
        body = merged_error_detail({"code": "bad_request"}, {"usage_accounting": {}})
        assert set(body) == {"detail", METADATA_KEY}
        assert body["detail"] == {"code": "bad_request"}


class TestRealCollectorIntegration:
    def test_never_dispatched_collector_renders_zero_attempts(self) -> None:
        collector = RequestAccountingCollector(
            provider="anthropic",
            requested_model="claude-haiku-4-5",
            transport="litellm_async_http",
        )
        metadata = _render(collector)
        assert metadata["usage_accounting"]["capture_status"] == "not_applicable"
        assert metadata["request_economics"]["observed_new_attempts"] == 0
