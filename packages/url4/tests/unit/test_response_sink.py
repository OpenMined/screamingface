"""The response-sink seam: ``url4.observe.current_response_sink()`` lets a
ctx-less world handler (e.g. the aigateway connector in ``apps/url4-cloud``)
report a model call's ``finish_reason`` and provider ``refusal`` tied to the
current node's span, without holding an
:class:`~url4.dag.node.ExecutionContext`.

FEATURE: a provider refusal must be distinguishable from a bad answer, so a
safety-refusing model is not scored as if it answered badly (OME-679).
STORY: as a researcher running HealthBench, I can audit exactly why each model
call ended — ``stop`` vs ``length`` vs ``content_filter``.

Every test drives the real :func:`~url4.dag.run` against a
:class:`~url4.io.static.StaticIOLayer` world with hand-built nodes — no mocking
of the executor itself, so these exercise the actual scheduling path. Mirrors
``test_usage_sink.py``, whose seam this one is modelled on.
"""

from __future__ import annotations

import asyncio

import pytest

from url4.dag import run
from url4.io.static import StaticIOLayer
from url4.observe import (
    ModelResponse,
    NodeStarted,
    ObservationEvent,
    current_response_sink,
)


class RecordingObserver:
    """Collects every emitted event, in emission order."""

    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def on_event(self, event: ObservationEvent) -> None:
        self.events.append(event)


class _RaisingObserver:
    """Raises on the first event — an embedder bug should be loud, not swallowed."""

    def __init__(self) -> None:
        self.error = RuntimeError("observer exploded")

    def on_event(self, event: ObservationEvent) -> None:
        raise self.error


class _SinkReportingNode:
    """A hand-built node reporting a finish reason through
    ``current_response_sink()`` rather than ``ctx.report_response`` — the
    ctx-less path a world adapter uses.

    ``seen_sink`` stashes whatever the lookup returned during ``resolve`` (a
    sentinel separates "not yet resolved" from "resolved and saw None"), so
    tests can assert on the ctx-less lookup itself, not only its side effect.
    """

    deps: dict = {}

    _UNRESOLVED = object()

    def __init__(
        self,
        *,
        finish_reason: str | None = "stop",
        refusal: str | None = None,
        delay: float = 0.0,
    ) -> None:
        self.finish_reason = finish_reason
        self.refusal = refusal
        self.delay = delay
        self.seen_sink: object = self._UNRESOLVED

    async def resolve(self, inputs, ctx):
        if self.delay:
            await asyncio.sleep(self.delay)
        sink = current_response_sink()
        self.seen_sink = sink
        if sink is not None:
            sink(finish_reason=self.finish_reason, refusal=self.refusal)
        return "ok"


class _CtxReportingNode:
    """Reports through ``ctx.report_response`` directly — the path an in-tree
    node uses, proving the context method and the sink land the same event."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        ctx.report_response(finish_reason="length", refusal=None)
        return "ok"


class _FailingAfterReportNode:
    """Reports, then raises — exercises the binding's reset on the error path."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        sink = current_response_sink()
        assert sink is not None
        sink(finish_reason="content_filter", refusal="I can't help with that")
        raise RuntimeError("node exploded")


class _MultiReportNode:
    """Reports twice in one resolve — the web-tool loop's normal shape, where a
    single node makes several model round trips."""

    deps: dict = {}

    async def resolve(self, inputs, ctx):
        sink = current_response_sink()
        assert sink is not None
        sink(finish_reason="tool_calls", refusal=None)
        sink(finish_reason="stop", refusal=None)
        return "ok"


class _JoinNode:
    """A fan-out root joining two labeled deps, reporting nothing of its own."""

    def __init__(self, deps: dict) -> None:
        self.deps = deps

    async def resolve(self, inputs, ctx):
        return "joined"


@pytest.mark.asyncio
async def test_sink_reaches_a_ctx_less_caller() -> None:
    # Behavior 1: current_response_sink() inside resolve -> a ModelResponse
    # event carrying that node's span_id.
    io = StaticIOLayer()
    rec = RecordingObserver()
    node = _SinkReportingNode(finish_reason="stop", refusal=None)
    result = await run(node, io, observer=rec)
    assert result == "ok"

    responses = [e for e in rec.events if isinstance(e, ModelResponse)]
    assert len(responses) == 1
    response = responses[0]
    assert response.finish_reason == "stop"
    assert response.refusal is None

    node_starts = [e for e in rec.events if isinstance(e, NodeStarted)]
    assert len(node_starts) == 1
    assert response.span_id == node_starts[0].span_id


@pytest.mark.asyncio
async def test_refusal_is_carried_verbatim() -> None:
    # Behavior 2: a content_filter turn carries BOTH the finish reason and the
    # provider's refusal text — the pair OME-679 needs to tell a refusal from a
    # bad answer.
    io = StaticIOLayer()
    rec = RecordingObserver()
    node = _SinkReportingNode(finish_reason="content_filter", refusal="I can't help with that")
    await run(node, io, observer=rec)

    (response,) = [e for e in rec.events if isinstance(e, ModelResponse)]
    assert response.finish_reason == "content_filter"
    assert response.refusal == "I can't help with that"


@pytest.mark.asyncio
async def test_ctx_report_response_emits_the_same_event() -> None:
    # Behavior 3: ctx.report_response() during resolve -> a ModelResponse event
    # carrying that node's span_id, identical in shape to the sink path.
    io = StaticIOLayer()
    rec = RecordingObserver()
    result = await run(_CtxReportingNode(), io, observer=rec)
    assert result == "ok"

    (response,) = [e for e in rec.events if isinstance(e, ModelResponse)]
    assert response.finish_reason == "length"

    (node_start,) = [e for e in rec.events if isinstance(e, NodeStarted)]
    assert response.span_id == node_start.span_id


@pytest.mark.asyncio
async def test_no_observer_means_sink_is_none() -> None:
    # Behavior 4: no observer -> current_response_sink() is None inside resolve,
    # and the run still succeeds (the zero-cost null path a world adapter relies
    # on to stay observer-agnostic).
    io = StaticIOLayer()
    node = _SinkReportingNode()
    result = await run(node, io)
    assert result == "ok"
    assert node.seen_sink is None


@pytest.mark.asyncio
async def test_several_reports_from_one_node_all_land_on_its_span() -> None:
    # Behavior 5: one node, several model round trips -> one event each, in
    # order, all attributed to the same span. INVARIANT: the seam never collapses
    # a turn's calls into one; a tool loop's intermediate `tool_calls` and its
    # final `stop` are both auditable.
    io = StaticIOLayer()
    rec = RecordingObserver()
    await run(_MultiReportNode(), io, observer=rec)

    responses = [e for e in rec.events if isinstance(e, ModelResponse)]
    assert [r.finish_reason for r in responses] == ["tool_calls", "stop"]

    (node_start,) = [e for e in rec.events if isinstance(e, NodeStarted)]
    assert {r.span_id for r in responses} == {node_start.span_id}


@pytest.mark.asyncio
async def test_per_task_isolation_across_concurrent_nodes() -> None:
    # Behavior 6: two sibling nodes reporting concurrently -> each ModelResponse
    # carries ITS OWN node's span_id, no cross-talk.
    # INVARIANT: this is the property the ContextVar-per-asyncio.Task binding
    # exists to protect, and the reason it is bound around `resolve` only.
    io = StaticIOLayer()
    rec = RecordingObserver()
    node_a = _SinkReportingNode(finish_reason="length", delay=0.02)
    node_b = _SinkReportingNode(finish_reason="content_filter", refusal="nope", delay=0.0)
    root = _JoinNode({"a": node_a, "b": node_b})
    result = await run(root, io, observer=rec)
    assert result == "joined"

    assert node_a.seen_sink is not None
    assert node_b.seen_sink is not None

    node_starts = [e for e in rec.events if isinstance(e, NodeStarted)]
    sink_starts = [e for e in node_starts if e.node_kind == "_SinkReportingNode"]
    assert len(sink_starts) == 2

    responses = [e for e in rec.events if isinstance(e, ModelResponse)]
    assert len(responses) == 2
    span_by_reason = {r.finish_reason: r.span_id for r in responses}
    assert set(span_by_reason) == {"length", "content_filter"}
    assert span_by_reason["length"] != span_by_reason["content_filter"]
    assert set(span_by_reason.values()) == {e.span_id for e in sink_starts}


@pytest.mark.asyncio
async def test_sink_is_reset_after_resolve() -> None:
    # Behavior 7: after a run completes, current_response_sink() at top level is
    # None again — the ContextVar was reset, not leaked.
    io = StaticIOLayer()
    rec = RecordingObserver()
    assert current_response_sink() is None
    await run(_SinkReportingNode(), io, observer=rec)
    assert current_response_sink() is None


@pytest.mark.asyncio
async def test_sink_is_reset_when_the_node_raises() -> None:
    # Behavior 8: the binding is reset on the FAILURE path too — a node that
    # reports and then raises must not leak its sink past its own resolve.
    io = StaticIOLayer()
    rec = RecordingObserver()
    with pytest.raises(RuntimeError, match="node exploded"):
        await run(_FailingAfterReportNode(), io, observer=rec)
    assert current_response_sink() is None

    (response,) = [e for e in rec.events if isinstance(e, ModelResponse)]
    assert response.finish_reason == "content_filter"


@pytest.mark.asyncio
async def test_observer_that_raises_fails_the_run_with_that_exception() -> None:
    # Behavior 9: an observer raising on a ModelResponse propagates out of the
    # run — the documented contract that an embedder bug is loud, not swallowed.
    io = StaticIOLayer()
    observer = _RaisingObserver()
    with pytest.raises(RuntimeError) as exc_info:
        await run(_SinkReportingNode(), io, observer=observer)
    assert exc_info.value is observer.error
