"""``Usage``'s cache/reasoning token classes and its priced ``cost_usd``.

FEATURE: per-run cost reporting (`OME-849`). The wire ``TokenUsage`` already carries five token
classes, but the observation event that feeds it carried two — so cache and reasoning tokens, and
the cost a provider authored, had no way to reach an embedder. This widens that seam.

STORY: as a researcher reading a run Report, I see what my prompt caching actually saved and what
the run cost, attributed to the node that spent it.

WHY the observation seam and not a side channel: span attribution comes from the sink the executor
binds around each node's ``resolve``, so a channel that bypasses it cannot say WHICH node spent the
money. See ``url4.dag.executor.Executor._eval``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from url4.dag import run
from url4.io.static import StaticIOLayer
from url4.observe import ObservationEvent, Usage, current_usage_sink


class _Recorder:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def on_event(self, event: ObservationEvent) -> None:
        self.events.append(event)


class _FullyAccountedNode:
    """Reports every class a gateway can observe, plus a priced cost."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        ctx.report_usage(
            provider="openrouter",
            model="openrouter/anthropic/claude-x",
            input_tokens=12480,
            output_tokens=742,
            response_model="anthropic/claude-x-20260801",
            cache_read_tokens=8000,
            cache_creation_tokens=4000,
            reasoning_tokens=610,
            cost_usd=Decimal("0.0413"),
        )
        return "ok"


class _TokensOnlyNode:
    """A provider that reports tokens but authors no cost — the Anthropic case."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        ctx.report_usage(
            provider="anthropic",
            model="claude-x",
            input_tokens=10,
            output_tokens=5,
        )
        return "ok"


class _SinkReportingNode:
    """Reports the widened fields through the ctx-less sink a world adapter uses."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        sink = current_usage_sink()
        assert sink is not None
        sink(
            provider="openrouter",
            model="m",
            input_tokens=1,
            output_tokens=2,
            cache_read_tokens=0,
            cost_usd=Decimal("0"),
        )
        return "ok"


def _usage(events: list[ObservationEvent]) -> Usage:
    usages = [e for e in events if isinstance(e, Usage)]
    assert len(usages) == 1
    return usages[0]


@pytest.mark.asyncio
async def test_every_token_class_and_the_cost_reach_the_event() -> None:
    rec = _Recorder()

    await run(_FullyAccountedNode(), StaticIOLayer(), observer=rec)

    usage = _usage(rec.events)
    assert usage.input_tokens == 12480
    assert usage.output_tokens == 742
    assert usage.cache_read_tokens == 8000
    assert usage.cache_creation_tokens == 4000
    assert usage.reasoning_tokens == 610
    assert usage.cost_usd == Decimal("0.0413")


@pytest.mark.asyncio
async def test_unreported_classes_stay_none_rather_than_zero() -> None:
    """INVARIANT: ``None`` means the provider did not say; ``0`` means it said zero.

    Collapsing the two would let an unknown cache class be priced as free — the exact failure the
    producing gateway's own contract is written to prevent.
    """
    rec = _Recorder()

    await run(_TokensOnlyNode(), StaticIOLayer(), observer=rec)

    usage = _usage(rec.events)
    assert usage.cache_read_tokens is None
    assert usage.cache_creation_tokens is None
    assert usage.reasoning_tokens is None
    assert usage.cost_usd is None


@pytest.mark.asyncio
async def test_an_explicit_zero_is_distinguishable_from_unreported() -> None:
    """A cache hit costs zero and reads zero cached tokens — both are real claims, not absences."""
    rec = _Recorder()

    await run(_SinkReportingNode(), StaticIOLayer(), observer=rec)

    usage = _usage(rec.events)
    assert usage.cache_read_tokens == 0
    assert usage.cost_usd == Decimal("0")
    assert usage.cache_creation_tokens is None


@pytest.mark.asyncio
async def test_the_cost_survives_as_an_exact_decimal() -> None:
    """INVARIANT: money is never coerced to float anywhere on this seam."""
    rec = _Recorder()

    class _PreciseNode:
        deps: dict = {}

        async def resolve(self, inputs, ctx):
            ctx.report_usage(
                provider="openrouter",
                model="m",
                input_tokens=1,
                output_tokens=1,
                cost_usd=Decimal("0.000000000000000001"),
            )
            return "ok"

    await run(_PreciseNode(), StaticIOLayer(), observer=rec)

    usage = _usage(rec.events)
    assert isinstance(usage.cost_usd, Decimal)
    assert usage.cost_usd == Decimal("0.000000000000000001")
