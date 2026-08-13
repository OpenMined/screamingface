"""Pure provider mapper tests for the evolving OME-303 accounting contract."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from litellm.types.utils import ModelResponse, Usage

from aigateway.plugins.anthropic_provider.usage_accounting import (
    cache_reference_from_cached as anthropic_cache_reference_from_cached,
)
from aigateway.plugins.anthropic_provider.usage_accounting import (
    normalize_anthropic_usage_accounting,
)
from aigateway.plugins.openrouter_provider.usage_accounting import (
    cache_reference_from_cached,
    normalize_openrouter_usage_accounting,
)
from aigateway.plugins.taxonomy.collector import RequestAccountingCollector
from aigateway.plugins.taxonomy.render import render_aigw_metadata


def _openrouter(raw: dict[str, Any] | None, final: dict[str, Any] | None = None, **kw: Any):
    return normalize_openrouter_usage_accounting(
        request_body={"model": "openrouter/x/y"}, raw_response=raw, final_response=final, **kw
    )


def _anthropic(raw: dict[str, Any] | None, final: dict[str, Any] | None = None, **kw: Any):
    return normalize_anthropic_usage_accounting(
        request_body={"model": "anthropic/claude"}, raw_response=raw, final_response=final, **kw
    )


def _litellm_final_usage(**usage: Any) -> dict[str, Any]:
    response = ModelResponse(
        id="msg_final", model="model/from-litellm", choices=[], usage=Usage(**usage)
    )
    return response.model_dump()


class TestOpenRouterCost:
    def test_usage_cost_becomes_reported_direct_cost_in_credits(self) -> None:
        cost = _openrouter(
            {
                "usage": {
                    "cost": Decimal("0.0012"),
                    "prompt_tokens": 56,
                    "completion_tokens": 41,
                }
            }
        ).direct_cost
        assert cost.as_json() == {
            "status": "reported",
            "amount": "0.0012",
            "unit": "openrouter_credits",
            "source": "openrouter.usage.cost",
        }

    def test_credits_are_never_labelled_usd(self) -> None:
        cost = _openrouter({"usage": {"cost": Decimal("1.5")}}).direct_cost
        assert cost.unit == "openrouter_credits"
        assert "usd" not in cost.unit

    def test_an_explicit_provider_zero_stays_zero(self) -> None:
        cost = _openrouter({"usage": {"cost": 0}}).direct_cost
        assert (cost.status, cost.amount) == ("reported", "0")

    def test_missing_and_invalid_cost_have_distinct_nonaggregable_statuses(self) -> None:
        assert _openrouter({"usage": {"prompt_tokens": 1}}).direct_cost.status == "unavailable"
        assert _openrouter({"usage": {"cost": None}}).direct_cost.status == "unavailable"
        assert _openrouter({"usage": {"cost": "NaN"}}).direct_cost.status == "invalid"

    @pytest.mark.parametrize(
        "cost", ["-1", "1000000000000000000", "0.1234567890123456789012345678901234"]
    )
    def test_invalid_cost_preserves_other_evidence(self, cost: str) -> None:
        evidence = _openrouter(
            {
                "id": "gen-1",
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "cost": cost},
            }
        )
        assert evidence.direct_cost.status == "invalid"
        assert evidence.usage.status == "complete"
        assert evidence.provider_response_id == "gen-1"

    def test_unitless_cost_details_are_bounded_audit_evidence(self) -> None:
        evidence = _openrouter(
            {
                "usage": {
                    "cost": 1,
                    "cost_details": {
                        "upstream_inference_cost": Decimal("0.8"),
                        "unknown_provider_text": "must-not-cross",
                    },
                }
            }
        )
        facts = evidence.provider_extensions[0].facts
        assert [fact.name for fact in facts] == ["upstream_inference_cost"]
        assert facts[0].kind == "decimal"
        assert facts[0].value == "0.8"
        assert facts[0].unit is None
        assert "must-not-cross" not in str(evidence)

    def test_converted_float_cost_and_cost_details_are_not_exact_evidence(self) -> None:
        evidence = _openrouter(
            None,
            {
                "usage": {
                    "prompt_tokens": 56,
                    "completion_tokens": 41,
                    "cost": 0.12345678901234568,
                    "cost_details": {"upstream_inference_cost": 0.1},
                }
            },
        )

        assert evidence.direct_cost.status == "unavailable"
        assert evidence.provider_extensions == ()
        assert evidence.usage.source == "provider_converted_response"
        assert (evidence.usage.input.total, evidence.usage.output.total) == (56, 41)

    def test_converted_float_never_reaches_request_subtotal(self) -> None:
        evidence = _openrouter(
            None,
            {
                "usage": {
                    "prompt_tokens": 56,
                    "completion_tokens": 41,
                    "cost": 0.12345678901234568,
                }
            },
        )
        collector = RequestAccountingCollector(
            provider="openrouter",
            requested_model="openrouter/x/y",
            transport="litellm_async_http",
        )
        collector.begin_dispatch()
        marker = object()
        collector.on_send_admitted(marker)
        collector.on_response_completed(marker, status=200, raw_evidence=None)
        collector.apply_evidence(collector.open_records()[0][0], evidence)

        economics = render_aigw_metadata(
            collector=collector,
            supported=True,
            cache_status="miss",
            gateway_call_id=collector.gateway_call_id,
        )["request_economics"]

        assert economics["direct_cost_status"] == "unavailable"
        assert economics["known_direct_cost_subtotals"] == []


class TestOpenRouterTokens:
    def test_maps_inclusive_totals_and_nonadditive_subsets(self) -> None:
        evidence = _openrouter(
            {
                "model": "x/y",
                "id": "gen-1",
                "usage": {
                    "prompt_tokens": 56,
                    "completion_tokens": 41,
                    "prompt_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 6},
                    "completion_tokens_details": {"reasoning_tokens": 8},
                    "cost": Decimal("0.5"),
                },
            }
        )
        usage = evidence.usage
        assert usage.input.total == 56
        assert usage.input.uncached == 30
        assert usage.input.cache_read == 20
        assert usage.input.cache_write == 6
        assert usage.output.total == 41
        assert usage.output.reasoning == 8
        assert usage.status == "complete"
        assert usage.source == "provider_raw_response"
        assert evidence.response_model == "x/y"
        assert evidence.provider_response_id == "gen-1"

    def test_absent_token_fields_stay_unknown(self) -> None:
        usage = _openrouter({"usage": {"prompt_tokens": 5}}).usage
        assert usage.input.total == 5
        assert usage.output.total is None
        assert usage.input.cache_read is None
        assert usage.output.reasoning is None
        assert usage.status == "partial"

    def test_raw_evidence_wins_over_zero_filled_converted_shape(self) -> None:
        usage = _openrouter(
            {"usage": {"prompt_tokens": 56, "completion_tokens": 41, "cost": 1}},
            {"usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}},
        ).usage
        assert (usage.input.total, usage.output.total) == (56, 41)
        assert usage.source == "provider_raw_response"

    def test_no_usage_is_unavailable_without_synthetic_zeros(self) -> None:
        evidence = _openrouter({"id": "gen-9"})
        assert evidence.usage.status == "unavailable"
        assert evidence.usage.input.total is None
        assert evidence.direct_cost.status == "unavailable"
        assert evidence.provider_response_id == "gen-9"

    def test_zero_filled_converted_totals_are_unknown(self) -> None:
        usage = _openrouter(None, _litellm_final_usage()).usage
        assert usage.status == "unavailable"
        assert usage.input.total is None
        assert usage.output.total is None

    def test_contradictory_cache_subsets_degrade_usage(self) -> None:
        usage = _openrouter(
            {
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 2,
                    "prompt_tokens_details": {"cached_tokens": 4, "cache_write_tokens": 3},
                }
            }
        ).usage
        assert usage.status == "partial"
        assert usage.input.uncached is None

    def test_reasoning_cannot_exceed_inclusive_output(self) -> None:
        usage = _openrouter(
            {
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 2,
                    "completion_tokens_details": {"reasoning_tokens": 3},
                }
            }
        ).usage
        assert usage.status == "partial"

    @pytest.mark.parametrize("value", [True, False, "12", 1.5, -1, 2**53, None])
    def test_invalid_token_values_are_refused(self, value: object) -> None:
        usage = _openrouter({"usage": {"prompt_tokens": value, "completion_tokens": 1}}).usage
        assert usage.input.total is None

    def test_explicit_zero_cache_write_is_not_absence(self) -> None:
        usage = _openrouter(
            {"usage": {"prompt_tokens": 1, "prompt_tokens_details": {"cache_write_tokens": 0}}}
        ).usage
        assert usage.input.cache_write == 0

    def test_litellm_cache_alias_is_honoured_only_as_fallback(self) -> None:
        usage = _openrouter(
            None,
            {"usage": {"prompt_tokens": 5, "prompt_tokens_details": {"cache_creation_tokens": 7}}},
        ).usage
        assert usage.input.cache_write == 7
        assert usage.source == "provider_converted_response"

    def test_litellm_zero_cache_details_are_unknown(self) -> None:
        usage = _openrouter(
            None,
            _litellm_final_usage(
                prompt_tokens=7,
                completion_tokens=3,
                total_tokens=10,
                prompt_tokens_details={"cached_tokens": 0, "cache_write_tokens": 0},
            ),
        ).usage
        assert usage.input.cache_read is None
        assert usage.input.cache_write is None


class TestOpenRouterCacheReference:
    def test_cached_final_response_keeps_usage_without_claiming_exact_cost(self) -> None:
        reference = cache_reference_from_cached(
            {"usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.0012}}
        )
        assert reference is not None
        assert reference.coverage == "final_successful_response_only"
        assert reference.incurred_in_current_request is False
        assert reference.usage.source == "cached_converted_response"
        assert reference.direct_cost.status == "unavailable"
        assert reference.direct_cost.amount is None

    def test_cached_body_without_usage_has_no_reference(self) -> None:
        assert cache_reference_from_cached({"choices": []}) is None

    def test_zero_filled_cached_usage_is_unknown_not_free(self) -> None:
        reference = cache_reference_from_cached(
            {"usage": {"prompt_tokens": 0, "completion_tokens": 0}}
        )
        assert reference is not None
        assert reference.usage.status == "unavailable"
        assert reference.usage.input.total is None


class TestAnthropic:
    def test_raw_input_total_includes_cache_reads_and_writes(self) -> None:
        evidence = _anthropic(
            {
                "model": "claude-haiku-4-5",
                "id": "msg_1",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 20,
                    "output_tokens_details": {"thinking_tokens": 7},
                },
            }
        )
        usage = evidence.usage
        assert usage.input.as_json() == {
            "total": 130,
            "uncached": 100,
            "cache_read": 20,
            "cache_write": 10,
            "cache_write_by_ttl": [],
        }
        assert usage.output.as_json() == {"total": 25, "reasoning": 7}
        assert usage.status == "complete"
        assert evidence.response_model == "claude-haiku-4-5"
        assert evidence.provider_response_id == "msg_1"

    def test_ttl_breakdown_is_pricing_relevant_and_must_match_cache_write(self) -> None:
        evidence = _anthropic(
            {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 0,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 7,
                        "ephemeral_1h_input_tokens": 3,
                    },
                }
            }
        )
        assert [row.as_json() for row in evidence.usage.input.cache_write_by_ttl] == [
            {"ttl_seconds": 300, "tokens": 7},
            {"ttl_seconds": 3600, "tokens": 3},
        ]
        assert evidence.usage.status == "complete"

        mismatch = _anthropic(
            {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "cache_creation_input_tokens": 11,
                    "cache_read_input_tokens": 0,
                    "cache_creation": {"ephemeral_5m_input_tokens": 7},
                }
            }
        )
        assert mismatch.usage.status == "partial"

    def test_service_tier_is_canonical_pricing_context(self) -> None:
        assert (
            _anthropic({"usage": {"service_tier": "priority"}}).pricing_context.service_tier
            == "priority"
        )
        assert (
            _anthropic(
                {"usage": {"service_tier": "provider-new-value"}}
            ).pricing_context.service_tier
            is None
        )

    @pytest.mark.parametrize("service_tier", [["standard"], {"tier": "standard"}])
    def test_malformed_service_tier_does_not_erase_other_evidence(
        self, service_tier: object
    ) -> None:
        evidence = _anthropic(
            {
                "id": "msg_1",
                "usage": {
                    "input_tokens": 1,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "output_tokens": 2,
                    "service_tier": service_tier,
                },
            }
        )
        assert evidence.pricing_context.service_tier is None
        assert evidence.usage.input.total == 1
        assert evidence.usage.output.total == 2
        assert evidence.provider_response_id == "msg_1"

    def test_direct_cost_is_contractually_absent_not_unknown(self) -> None:
        assert _anthropic({"usage": {"input_tokens": 1}}).direct_cost.status == "absent"
        assert _anthropic(None).direct_cost.status == "absent"

    def test_absent_cache_subsets_remain_unknown(self) -> None:
        usage = _anthropic({"usage": {"input_tokens": 1, "output_tokens": 1}}).usage
        assert usage.input.total is None
        assert usage.input.cache_read is None
        assert usage.input.cache_write is None
        assert usage.status == "partial"

    def test_converted_usage_is_labelled_and_zero_details_are_unknown(self) -> None:
        usage = _anthropic(
            None,
            _litellm_final_usage(
                prompt_tokens=130,
                completion_tokens=25,
                total_tokens=155,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                completion_tokens_details={"reasoning_tokens": 7},
            ),
        ).usage
        assert usage.source == "provider_converted_response"
        assert usage.input.total == 130
        assert usage.output.total == 25
        assert usage.input.cache_read is None
        assert usage.input.cache_write is None
        # LiteLLM derives this value locally from summarized thinking text. It is not
        # provider-reported Anthropic usage and cannot populate the canonical subset.
        assert usage.output.reasoning is None

    def test_converted_and_cached_usage_preserve_litellm_cache_breakdown(self) -> None:
        final = _litellm_final_usage(
            prompt_tokens=130,
            completion_tokens=25,
            total_tokens=155,
            prompt_tokens_details={
                "text_tokens": 100,
                "cached_tokens": 20,
                "cache_creation_tokens": 10,
                "cache_creation_token_details": {
                    "ephemeral_5m_input_tokens": 7,
                    "ephemeral_1h_input_tokens": 3,
                },
            },
        )

        converted = _anthropic(None, final).usage
        cached = anthropic_cache_reference_from_cached(final)

        assert converted.input.as_json() == {
            "total": 130,
            "uncached": 100,
            "cache_read": 20,
            "cache_write": 10,
            "cache_write_by_ttl": [
                {"ttl_seconds": 300, "tokens": 7},
                {"ttl_seconds": 3600, "tokens": 3},
            ],
        }
        assert cached is not None
        assert cached.usage.input.as_json() == converted.input.as_json()

    def test_zero_filled_converted_totals_are_unknown(self) -> None:
        usage = _anthropic(None, _litellm_final_usage()).usage
        assert usage.status == "unavailable"
        assert usage.input.total is None
        assert usage.output.total is None

    def test_inclusive_input_overflow_degrades_without_losing_output(self) -> None:
        usage = _anthropic(
            {
                "usage": {
                    "input_tokens": 2**53 - 1,
                    "cache_read_input_tokens": 1,
                    "output_tokens": 2,
                }
            }
        ).usage
        assert usage.status == "partial"
        assert usage.input.total is None
        assert usage.output.total == 2

    def test_reasoning_cannot_exceed_inclusive_output(self) -> None:
        usage = _anthropic(
            {
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "output_tokens_details": {"thinking_tokens": 3},
                }
            }
        ).usage
        assert usage.status == "partial"

    def test_safe_usage_survives_a_failed_outcome(self) -> None:
        evidence = _anthropic(
            {
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                }
            },
            failed=True,
        )
        assert evidence.usage.status == "complete"
        assert evidence.usage.input.total == 1

    def test_server_tool_counts_are_allowlisted_audit_evidence(self) -> None:
        evidence = _anthropic(
            {
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "server_tool_use": {
                        "web_search_requests": 2,
                        "raw_text": "must-not-cross",
                    },
                }
            }
        )
        facts = evidence.provider_extensions[0].facts
        assert [fact.name for fact in facts] == ["web_search_requests"]
        assert facts[0].value == 2
        assert "must-not-cross" not in str(evidence)

    def test_positive_converted_cache_usage_survives_as_historical_evidence(self) -> None:
        reference = anthropic_cache_reference_from_cached(
            _litellm_final_usage(
                prompt_tokens=130,
                completion_tokens=25,
                total_tokens=155,
                cache_creation_input_tokens=10,
                cache_read_input_tokens=20,
            )
        )
        assert reference is not None
        assert reference.usage.status == "complete"
        assert reference.usage.input.total == 130
        assert reference.usage.output.total == 25
        assert reference.usage.input.cache_read == 20
        assert reference.usage.input.cache_write == 10
        assert reference.direct_cost.status == "absent"
