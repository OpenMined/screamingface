"""The usage-sink seam: ``url4.observe.current_usage_sink()`` lets a ctx-less
world handler (e.g. a future aigateway connector) report model token usage
tied to the current node's span, without holding an
:class:`~url4.dag.node.ExecutionContext`.

Every test drives the real :func:`~url4.dag.run` against a
:class:`~url4.io.static.StaticIOLayer` world with hand-built nodes — no
mocking of the executor itself, so these tests exercise the actual
scheduling/memoization path (mirrors ``test_observe.py``'s ``_UsageNode``,
except the node here goes through ``current_usage_sink()`` instead of
``ctx.report_usage`` directly, proving the ctx-less path).
"""

from __future__ import annotations

import asyncio

import pytest

from url4.dag import run
from url4.io.static import StaticIOLayer
from url4.observe import NodeStarted, ObservationEvent, Usage, current_usage_sink


class RecordingObserver:
    """Collects every emitted event, in emission order."""

    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def on_event(self, event: ObservationEvent) -> None:
        self.events.append(event)


class _SinkReportingNode:
    """A hand-built node that reports usage through ``current_usage_sink()``
    instead of ``ctx.report_usage`` — the ctx-less path a world adapter uses.

    ``seen_sink`` stashes whatever ``current_usage_sink()`` returned during
    ``resolve`` (a sentinel distinguishes "not yet resolved" from "resolved
    and saw None"), so tests can assert on the ctx-less lookup itself, not
    just its side effect.
    """

    deps: dict = {}

    _UNRESOLVED = object()

    def __init__(
        self,
        *,
        provider: str = "p",
        model: str = "m",
        input_tokens: int = 3,
        output_tokens: int = 5,
        delay: float = 0.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.delay = delay
        self.seen_sink: object = self._UNRESOLVED

    async def resolve(self, inputs, ctx):
        if self.delay:
            await asyncio.sleep(self.delay)
        sink = current_usage_sink()
        self.seen_sink = sink
        if sink is not None:
            sink(
                provider=self.provider,
                model=self.model,
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
            )
        return "ok"


class _JoinNode:
    """A hand-built node joining two labeled deps — a fan-out root with no
    usage reporting of its own."""

    def __init__(self, deps: dict) -> None:
        self.deps = deps

    async def resolve(self, inputs, ctx):
        return "joined"


@pytest.mark.asyncio
async def test_sink_reaches_a_ctx_less_caller() -> None:
    # Behavior 1: current_usage_sink() inside resolve -> a Usage event
    # carrying that node's span_id.
    io = StaticIOLayer()
    rec = RecordingObserver()
    node = _SinkReportingNode(provider="p", model="m", input_tokens=3, output_tokens=5)
    result = await run(node, io, observer=rec)
    assert result == "ok"

    usages = [e for e in rec.events if isinstance(e, Usage)]
    assert len(usages) == 1
    usage = usages[0]
    assert usage.provider == "p"
    assert usage.model == "m"
    assert usage.input_tokens == 3
    assert usage.output_tokens == 5

    node_starts = [e for e in rec.events if isinstance(e, NodeStarted)]
    assert len(node_starts) == 1
    assert usage.span_id == node_starts[0].span_id


@pytest.mark.asyncio
async def test_no_observer_means_sink_is_none() -> None:
    # Behavior 2: no observer -> current_usage_sink() is None inside resolve,
    # and the run still succeeds (the zero-cost null path).
    io = StaticIOLayer()
    node = _SinkReportingNode()
    result = await run(node, io)
    assert result == "ok"
    assert node.seen_sink is None


@pytest.mark.asyncio
async def test_per_task_isolation_across_concurrent_nodes() -> None:
    # Behavior 3: two sibling nodes reporting distinct usage concurrently ->
    # each Usage event carries ITS OWN node's span_id, no cross-talk.
    io = StaticIOLayer()
    rec = RecordingObserver()
    node_a = _SinkReportingNode(
        provider="a-provider", model="a-model", input_tokens=1, output_tokens=1, delay=0.02
    )
    node_b = _SinkReportingNode(
        provider="b-provider", model="b-model", input_tokens=2, output_tokens=2, delay=0.0
    )
    root = _JoinNode({"a": node_a, "b": node_b})
    result = await run(root, io, observer=rec)
    assert result == "joined"

    assert node_a.seen_sink is not None
    assert node_b.seen_sink is not None

    # Two _SinkReportingNode spans among the started nodes (plus the join root).
    node_starts = [e for e in rec.events if isinstance(e, NodeStarted)]
    sink_starts = [e for e in node_starts if e.node_kind == "_SinkReportingNode"]
    assert len(sink_starts) == 2

    usages = [e for e in rec.events if isinstance(e, Usage)]
    assert len(usages) == 2
    by_provider = {u.provider: u for u in usages}
    assert set(by_provider) == {"a-provider", "b-provider"}

    span_by_provider = {u.provider: u.span_id for u in usages}
    assert span_by_provider["a-provider"] != span_by_provider["b-provider"]

    span_ids_started = {e.span_id for e in sink_starts}
    assert set(span_by_provider.values()) == span_ids_started


@pytest.mark.asyncio
async def test_sink_is_reset_after_resolve() -> None:
    # Behavior 4: after a run completes, current_usage_sink() at top level is
    # None again — the ContextVar was reset, not leaked.
    io = StaticIOLayer()
    rec = RecordingObserver()
    assert current_usage_sink() is None
    await run(_SinkReportingNode(), io, observer=rec)
    assert current_usage_sink() is None
