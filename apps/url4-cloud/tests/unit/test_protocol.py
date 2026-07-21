from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from url4_cloud_protocol import (
    CostBreakdown,
    CostUsage,
    OutboundFrameAdapter,
    Span,
    TokenUsage,
)


def _ts() -> datetime:
    return datetime(2026, 7, 21, 9, 0, 0)


def test_cost_total_must_equal_sum() -> None:
    with pytest.raises(ValidationError):
        CostBreakdown(
            input_usd=Decimal("0.01"), output_usd=Decimal("0.02"), total_usd=Decimal("0.99")
        )


def test_cost_total_equals_sum_ok() -> None:
    cb = CostBreakdown(
        input_usd=Decimal("0.018"), output_usd=Decimal("0.0255"), total_usd=Decimal("0.0435")
    )
    assert cb.total_usd == Decimal("0.0435")


def test_discriminated_union_parses_by_type() -> None:
    frame = OutboundFrameAdapter.validate_python(
        {
            "type": "cost.usage",
            "trace_id": "t",
            "node_id": "n",
            "ts": _ts(),
            "scope": "self",
            "provider": "anthropic",
            "model": "m",
            "pricing_version": "2026-07-01",
            "usage": {"input_tokens": 10},
            "cost": {"total_usd": "0"},
        }
    )
    assert isinstance(frame, CostUsage)
    assert frame.scope == "self"


def test_money_serializes_as_string() -> None:
    cu = CostUsage(
        trace_id="t",
        node_id="n",
        ts=_ts(),
        scope="self",
        provider="p",
        model="m",
        pricing_version="v",
        usage=TokenUsage(),
        cost=CostBreakdown(total_usd=Decimal("0")),
    )
    dumped = cu.model_dump(mode="json")
    assert isinstance(dumped["cost"]["total_usd"], str)


def test_span_has_tokens_not_cost() -> None:
    span = Span(
        trace_id="t",
        node_id="n",
        ts=_ts(),
        name="chat",
        operation="chat",
        start_ts=_ts(),
        input_tokens=100,
        output_tokens=50,
    )
    fields = span.model_dump()
    assert fields["input_tokens"] == 100
    assert "cost" not in fields
