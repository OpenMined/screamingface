"""The response seam carries a call's CACHE outcome alongside how it ended.

FEATURE: url4 per-run cache policy (spec §7, D7) — a turn served from a gateway's response
cache costs nothing upstream, so a run that cannot report the outcome bills a hit as a fresh
call. That error HIDES savings, which is why nobody ever reports it.
STORY: as an operator who turned caching on, I can see per span whether the call hit, missed or
bypassed the cache, and — when it did not hit — the gateway's own reason for it.

WHY this rides the EXISTING `ModelResponse` seam rather than a new event kind: the fact is
per-round-trip, exactly like `finish_reason`, and a world adapter learns both from the same
response. A second event would double the seam and force consumers to correlate two streams to
answer one question about one call.

A separate module from `test_response_sink.py` rather than an append: the repo's append-only
gate compares file status, so growing an existing test file reads as "a prior test was
modified" even when the diff is purely additive (same reason `test_finish_reason_capture.py`
exists next to `test_aigateway_connector.py` in url4-cloud).
"""

from __future__ import annotations

import pytest

from url4.dag import run
from url4.io.static import StaticIOLayer
from url4.observe import ModelResponse, NodeStarted, ObservationEvent, current_response_sink


class _Recorder:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def on_event(self, event: ObservationEvent) -> None:
        self.events.append(event)


class _CacheReportingNode:
    """Reports a cache outcome through the ctx-less sink — the path the aigateway connector
    takes, since it holds an HTTP response and no `ExecutionContext`."""

    deps: dict = {}

    def __init__(self, *, cache_status: str | None, cache_reason: str | None) -> None:
        self.cache_status = cache_status
        self.cache_reason = cache_reason

    async def resolve(self, inputs, ctx):
        sink = current_response_sink()
        assert sink is not None
        sink(
            finish_reason="stop",
            refusal=None,
            cache_status=self.cache_status,
            cache_reason=self.cache_reason,
        )
        return "ok"


class _LegacyReportingNode:
    """Reports the two ORIGINAL fields only — every caller written before the cache outcome
    existed, which must keep working unchanged."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        sink = current_response_sink()
        assert sink is not None
        sink(finish_reason="stop", refusal=None)
        return "ok"


class _CtxCacheReportingNode:
    """Reports through `ctx.report_response` — the in-tree path, which must land the same
    event as the ctx-less sink."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        ctx.report_response(
            finish_reason="stop", refusal=None, cache_status="bypass", cache_reason="opted_out"
        )
        return "ok"


class _MultiCacheReportNode:
    """Two round trips in one resolve — the web-tool loop's normal shape. Each carries its own
    cache outcome, because each is an independently-keyed gateway call."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        sink = current_response_sink()
        assert sink is not None
        sink(finish_reason="tool_calls", refusal=None, cache_status="hit", cache_reason=None)
        sink(finish_reason="stop", refusal=None, cache_status="miss", cache_reason=None)
        return "ok"


def _responses(rec: _Recorder) -> list[ModelResponse]:
    return [e for e in rec.events if isinstance(e, ModelResponse)]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["hit", "miss", "bypass"])
async def test_every_cache_status_reaches_the_observer(status: str) -> None:
    rec = _Recorder()
    node = _CacheReportingNode(cache_status=status, cache_reason=None)
    await run(node, StaticIOLayer(), observer=rec)

    (response,) = _responses(rec)
    assert response.cache_status == status


@pytest.mark.asyncio
async def test_the_gateways_reason_is_carried_verbatim() -> None:
    # INVARIANT: the gateway's vocabulary, not ours. Normalising it here would erase exactly the
    # distinction that answers "I asked for no caching and something still cached".
    rec = _Recorder()
    await run(
        _CacheReportingNode(cache_status="bypass", cache_reason="unsupported_control"),
        StaticIOLayer(),
        observer=rec,
    )

    (response,) = _responses(rec)
    assert response.cache_reason == "unsupported_control"


@pytest.mark.asyncio
async def test_a_caller_that_reports_no_cache_outcome_still_works() -> None:
    # INVARIANT: this seam is a live contract with callers already written against it (and the
    # engine's own `ctx.report_response`). Widening it must not require any of them to change,
    # and an absent outcome must read as "nothing reported" rather than a fabricated status.
    rec = _Recorder()
    await run(_LegacyReportingNode(), StaticIOLayer(), observer=rec)

    (response,) = _responses(rec)
    assert response.finish_reason == "stop"
    assert response.cache_status is None
    assert response.cache_reason is None


@pytest.mark.asyncio
async def test_ctx_report_response_carries_the_outcome_too() -> None:
    rec = _Recorder()
    await run(_CtxCacheReportingNode(), StaticIOLayer(), observer=rec)

    (response,) = _responses(rec)
    assert (response.cache_status, response.cache_reason) == ("bypass", "opted_out")

    (node_start,) = [e for e in rec.events if isinstance(e, NodeStarted)]
    assert response.span_id == node_start.span_id


@pytest.mark.asyncio
async def test_each_round_trip_reports_its_own_outcome() -> None:
    # INVARIANT: one node can make several gateway calls, and they are keyed independently — a
    # turn whose first call hit and whose continuation missed is two facts, not one.
    rec = _Recorder()
    await run(_MultiCacheReportNode(), StaticIOLayer(), observer=rec)

    assert [r.cache_status for r in _responses(rec)] == ["hit", "miss"]
