"""``run`` — the Runner's execute-and-publish orchestration (spec §1.1; docs/protocol.md §4).

Publishes the CloudEvents lifecycle to the injected :class:`~url4_cloud_nats.Bus`:
``Started`` → (``Log``/``Span``/``CostUsage{self}`` as available) → ``CostUsage{subtree}`` →
``Result`` → ``Terminated{succeeded}``; any exception funnels to ``Terminated{failed}`` with an
:class:`~url4_streaming_protocol.ErrorInfo`. The :class:`~url4_cloud_runner.executor.Executor`
and the ``Bus`` are injected so tests drive a stub executor + in-memory bus (no url4/network).

Every published frame carries a W3C ``traceparent`` (trace PRD §3.2.2): this module establishes
the run-root trace context up front — adopting a valid inbound ``traceparent`` (W3C "restart" rule:
malformed/absent never propagates, a fresh trace is minted instead) — and threads it into the
executor so real per-span identity (when the adapter provides it) and the CloudEvents wire fields
agree. See :func:`_trace_fields` for THE STAMPING RULES.
"""

import secrets
from datetime import UTC, datetime
from typing import Literal, TypedDict
from uuid import uuid4

from url4_cloud_nats import Bus
from url4_cloud_runner.executor import Completed, Executor, SpanRef, Telemetry, TraceContext, Traced
from url4_cloud_runner.trace import parse_traceparent
from url4_streaming_protocol import (
    CostUsageEvent,
    ErrorInfo,
    LogData,
    LogEvent,
    OutboundFrame,
    ResultEvent,
    SpanData,
    SpanEvent,
    StartedData,
    StartedEvent,
    TerminatedData,
    TerminatedEvent,
)


class _Envelope(TypedDict):
    """The CloudEvents attributes the Runner assigns per event (docs/protocol.md §1, §3, §6)."""

    id: str
    source: str
    subject: str
    time: datetime
    sequence: str
    sequencetype: Literal["Integer"]
    traceparent: str
    tracestate: str | None


class _IncompleteExecution(Exception):
    """The executor's stream ended without a terminal ``Completed`` — a malformed executor."""


class _Sequencer:
    """Stamps each event with a fresh envelope: uuid4 id, node source, monotonic string sequence,
    and the caller-supplied W3C trace fields."""

    def __init__(self, topic: str, node: str) -> None:
        # INVARIANT: source addresses the emitting node (docs/protocol.md §1); subject == the run.
        self._source = f"/trace/{topic}/node/{node}"
        self._subject = topic
        self._n = 0

    def next(self, traceparent: str, tracestate: str | None = None) -> _Envelope:
        self._n += 1
        return _Envelope(
            id=uuid4().hex,
            source=self._source,
            subject=self._subject,
            time=datetime.now(UTC),
            sequence=str(self._n),
            sequencetype="Integer",
            traceparent=traceparent,
            tracestate=tracestate,
        )


def _wrap_telemetry(env: _Envelope, data: Telemetry) -> OutboundFrame:
    if isinstance(data, LogData):
        return LogEvent(**env, data=data)
    if isinstance(data, SpanData):
        return SpanEvent(**env, data=data)
    return CostUsageEvent(**env, data=data)


def _error_info(exc: BaseException) -> ErrorInfo:
    # WHY: duck-type url4 Url4Error's code/permanent without importing url4 — the Runner stays
    # dependency-free; a non-url4 exception falls back to a permanent internal error.
    code = getattr(exc, "code", None)
    permanent = getattr(exc, "permanent", None)
    return ErrorInfo(
        code=code if isinstance(code, str) else "internal_error",
        message=str(exc) or exc.__class__.__name__,
        permanent=permanent if isinstance(permanent, bool) else True,
    )


def _root_traceparent(root_ctx: TraceContext) -> str:
    return f"00-{root_ctx.trace_id}-{root_ctx.root_span_id}-01"


def _trace_fields(
    payload: Telemetry, span_ref: SpanRef | None, root_ctx: TraceContext, root_tp: str
) -> tuple[str, str | None]:
    """THE STAMPING RULES (trace PRD §3.2.2).

    A span frame with real per-span identity (``span_ref`` set — only ``Url4Executor`` provides
    this) gets its own ``traceparent`` and a ``tracestate`` naming its parent, UNLESS its parent
    collapses onto the run-root (``None``, or exactly ``root_ctx.root_span_id``) — the root-collapse
    that makes the real span tree match ``mock_runner``'s ``root ← {leaf-0, leaf-1}`` edge set.
    Everything else — non-span frames, AND a bare-``Telemetry`` executor's ``SpanData`` with no
    identity to stamp — carries the
    run-root ``traceparent`` (``root_tp``, precomputed once in :func:`run`) with no ``tracestate``:
    the whole stream stays trace-searchable, not just the spans that carry real identity.
    """
    if isinstance(payload, SpanData) and span_ref is not None:
        traceparent = f"00-{root_ctx.trace_id}-{span_ref.span_id}-01"
        is_top_level = (
            span_ref.parent_span_id is None or span_ref.parent_span_id == root_ctx.root_span_id
        )
        if is_top_level:
            return traceparent, None
        return traceparent, f"url4.parent={span_ref.parent_span_id}"
    return root_tp, None


async def run(
    bus: Bus,
    executor: Executor,
    topic: str,
    url4: str,
    *,
    node: str = "root",
    traceparent: str | None = None,
) -> None:
    """Execute ``url4`` via ``executor`` and publish its CloudEvents lifecycle to ``bus``.

    ``traceparent``, when it strictly matches the W3C format, seeds the run's ``trace_id`` (the
    caller's trace is adopted); absent or malformed, a fresh ``trace_id`` is minted instead (W3C
    restart rule — garbage never propagates). ``root_span_id`` is always freshly minted here: this
    run is its own new span in the caller's trace, never a reused span id.
    """
    # WHY: the Runner is the producer; ensure the per-topic stream exists before the first publish
    # (idempotent; NatsBus.publish does not auto-create the stream).
    await bus.ensure_stream(topic)
    seq = _Sequencer(topic, node)
    inbound_trace_id = parse_traceparent(traceparent)
    root_ctx = TraceContext(
        trace_id=inbound_trace_id if inbound_trace_id is not None else secrets.token_hex(16),
        root_span_id=secrets.token_hex(8),
    )
    root_tp = _root_traceparent(root_ctx)
    try:
        await bus.publish(
            topic,
            StartedEvent(**seq.next(root_tp), data=StartedData(url4=url4)),
        )
        completed: Completed | None = None
        async for step in executor.execute(url4, trace=root_ctx):
            if isinstance(step, Completed):
                completed = step
                break
            if isinstance(step, Traced):
                payload, span_ref = step.payload, step.span
            else:
                payload, span_ref = step, None
            tp, ts = _trace_fields(payload, span_ref, root_ctx, root_tp)
            await bus.publish(topic, _wrap_telemetry(seq.next(tp, ts), payload))
        if completed is None:
            raise _IncompleteExecution("executor produced no Completed outcome")
        # INVARIANT: the pre-result roll-up is always scope="subtree" (spec §8), whatever came in.
        subtree = completed.subtree_cost.model_copy(update={"scope": "subtree"})
        await bus.publish(topic, CostUsageEvent(**seq.next(root_tp), data=subtree))
        await bus.publish(topic, ResultEvent(**seq.next(root_tp), data=completed.result))
        await bus.publish(
            topic, TerminatedEvent(**seq.next(root_tp), data=TerminatedData(status="succeeded"))
        )
    except Exception as exc:
        await bus.publish(
            topic,
            TerminatedEvent(
                **seq.next(root_tp), data=TerminatedData(status="failed", error=_error_info(exc))
            ),
        )
