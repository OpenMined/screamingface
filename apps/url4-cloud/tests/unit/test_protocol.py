from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from url4_streaming_protocol import (
    CostBreakdown,
    CostUsageData,
    CostUsageEvent,
    OutboundFrameAdapter,
    SpanData,
    SpanEvent,
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


def test_cloudevent_parses_by_type_with_gen_ai_aliases() -> None:
    frame = OutboundFrameAdapter.validate_python(
        {
            "specversion": "1.0",
            "id": "e1",
            "source": "/trace/t/node/root",
            "type": "ai.url4.cost.usage",
            "subject": "t",
            "time": _ts(),
            "sequence": "7",
            "sequencetype": "Integer",
            "data": {
                "scope": "self",
                "gen_ai.provider.name": "anthropic",
                "gen_ai.response.model": "claude-opus-4-8",
                "pricing_version": "2026-07-01",
                "usage": {"gen_ai.usage.input_tokens": 10},
                "cost": {"total_usd": "0"},
            },
        }
    )
    assert isinstance(frame, CostUsageEvent)
    assert frame.specversion == "1.0"
    assert frame.data.scope == "self"
    assert frame.data.provider == "anthropic"
    assert frame.data.usage.input_tokens == 10


def test_span_dumps_gen_ai_keys_and_no_cost() -> None:
    span = SpanEvent(
        id="e2",
        source="/trace/t/node/n",
        data=SpanData(
            name="chat", operation="chat", input_tokens=100, output_tokens=50, start=_ts()
        ),
    )
    dumped = span.model_dump(mode="json", by_alias=True)
    assert dumped["type"] == "ai.url4.span"
    assert dumped["data"]["gen_ai.usage.input_tokens"] == 100
    assert "cost" not in dumped["data"]


def test_money_serializes_as_string() -> None:
    ev = CostUsageEvent(
        id="e3",
        source="/trace/t/node/n",
        data=CostUsageData(
            scope="self",
            provider="p",
            model="m",
            pricing_version="v",
            usage=TokenUsage(),
            cost=CostBreakdown(total_usd=Decimal("0")),
        ),
    )
    dumped = ev.model_dump(mode="json", by_alias=True)
    assert isinstance(dumped["data"]["cost"]["total_usd"], str)
