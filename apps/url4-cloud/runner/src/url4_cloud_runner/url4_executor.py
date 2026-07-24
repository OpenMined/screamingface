"""``Url4Executor`` — the real url4-engine-backed :class:`Executor` (spec §1.1, OME-446).

The ONLY module in ``url4-cloud`` allowed to import ``url4`` (contract C6): the engine is a
plugin behind the :class:`~url4_cloud_runner.executor.Executor` port, and nothing else in this
app may reach into it directly. This module bridges ``url4.observe``'s synchronous, inline
:class:`~url4.observe.Observer` callback (called from the engine's own asyncio tasks, on the
same loop, never awaited) onto the async generator :meth:`Url4Executor.execute` the Runner
consumes — a classic sync-producer/async-consumer bridge (:class:`_Bridge`), because
``Observer.on_event`` MUST NOT block or await (the engine calls it inline from its scheduling
hot path) while the Runner's :mod:`~url4_cloud_runner.publish` wants to await each frame as it
publishes it.

Span identity (``span_id``/``parent_span_id``) is threaded out per span frame as a
:class:`~url4_cloud_runner.executor.SpanRef` alongside its
:class:`~url4_cloud_runner.executor.Traced` wrapper; :mod:`~url4_cloud_runner.publish` is what
turns that identity into the wire ``traceparent``/``tracestate`` fields (spec traceparent PRD
§3.2.2) — this module only carries the raw ids, never touching the CloudEvents envelope itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from url4.dag import run as url4_run
from url4.io.layer import IOLayer
from url4.io.static import StaticIOLayer
from url4.observe import (
    Log,
    NodeFinished,
    NodeStarted,
    ObservationEvent,
    RunStarted,
    Usage,
)

from url4_cloud_runner.executor import Completed, ExecStep, SpanRef, TraceContext, Traced
from url4_streaming_protocol import CostUsageData, LogData, ResultData, SpanData, TokenUsage
from url4_streaming_protocol.taxonomy import CostBreakdown

_logger = logging.getLogger(__name__)

_TRUNCATION_MARKER = "…[truncated]"

# OTel SeverityNumber per docs/protocol.md §5.2; unrecognized severities default to INFO/9.
_SEVERITY: dict[str, tuple[int, Literal["DEBUG", "INFO", "WARN", "ERROR"]]] = {
    "DEBUG": (5, "DEBUG"),
    "INFO": (9, "INFO"),
    "WARN": (13, "WARN"),
    "ERROR": (17, "ERROR"),
}


class BridgeOverflowError(RuntimeError):
    """The event backlog stayed over its hard cap even after evicting every droppable ``Log``.

    Only Span/Usage/lifecycle events (never dropped, by design — see :class:`_Bridge`) can
    cause this: the consumer is falling behind production faster than Log eviction alone can
    bound the buffer. Raised from ``on_event``, so it propagates out of the run exactly like
    any other :class:`~url4.observe.Observer` failure (url4.observe's own contract) — failing
    the run loudly beats growing ``_buf`` without limit until the process OOMs.
    """


class _Bridge:
    """Sync producer (``Observer.on_event``, called from engine tasks on the same loop) → async
    single consumer. Bounded with a PRIORITY DROP policy: never drop Span/Usage/lifecycle
    events (``NodeStarted``/``NodeFinished``/``Usage``/``RunStarted``/``RunFinished``); drop
    ``Log`` first — telemetry logs are the only event kind whose loss is tolerable, since
    dropping a span or a cost report would corrupt the §8 CloudEvents lifecycle invariants.

    ``maxsize`` alone only bounds Log volume — a burst of Span/Usage/lifecycle events with no
    Logs present to evict can still grow the buffer past it. ``_hard_cap`` (a multiple of
    ``maxsize``, giving a slow consumer real headroom beyond one Log-bounded fill) is the true
    ceiling: crossing it raises :class:`BridgeOverflowError` instead of growing forever.

    INVARIANT: ``on_event`` never awaits — the engine emits synchronously and inline, from
    whichever of its own asyncio tasks is currently resolving a node. Since this all runs on one
    event loop with no ``await`` between the ``len()`` check and the ``append``, the buffer
    mutation is atomic with respect to the async consumer (mirrors the DAG executor's own
    check-then-act discipline for its memo dict).
    """

    _HARD_CAP_MULTIPLIER = 8

    def __init__(self, maxsize: int) -> None:
        self._buf: deque[ObservationEvent] = deque()
        self._max = maxsize
        self._hard_cap = maxsize * self._HARD_CAP_MULTIPLIER
        self._dropped = 0
        self._closed = False
        self._wake = asyncio.Event()

    @property
    def dropped(self) -> int:
        return self._dropped

    def on_event(self, event: ObservationEvent) -> None:
        if len(self._buf) >= self._max:
            if isinstance(event, Log):
                self._dropped += 1
                return  # drop the incoming Log; never even enters the buffer
            self._evict_oldest_log()
        if len(self._buf) >= self._hard_cap:
            raise BridgeOverflowError(
                f"event backlog exceeded the hard cap ({self._hard_cap} events, "
                f"{self._dropped} Log(s) already dropped) — the consumer is not keeping up"
            )
        self._buf.append(event)
        self._wake.set()

    def _evict_oldest_log(self) -> None:
        # Buffer is at (or over) capacity and the incoming event is NOT a Log (a Span/Usage/
        # lifecycle event we must never drop): make room by evicting the oldest Log present, or
        # — if the buffer holds no Log at all — accept the soft-cap overflow and append anyway.
        for i, buffered in enumerate(self._buf):
            if isinstance(buffered, Log):
                del self._buf[i]
                self._dropped += 1
                return

    def close(self) -> None:
        self._closed = True
        self._wake.set()

    async def drain(self) -> AsyncIterator[ObservationEvent]:
        while True:
            if self._buf:
                yield self._buf.popleft()
                continue
            if self._closed:
                return
            self._wake.clear()
            await self._wake.wait()


@dataclass
class _SpanState:
    """Bookkeeping for one open span, from ``NodeStarted`` until its ``NodeFinished``."""

    kind: str
    detail: str
    start: datetime
    parent_span_id: str | None
    usage: tuple[str, str, int, int] | None = field(default=None)


class _RunState:
    """Accumulates spans-in-flight and subtree usage totals; maps engine events to
    :class:`~url4_cloud_runner.executor.Traced` frames (§ event-mapping table)."""

    def __init__(self) -> None:
        self.trace_id: str | None = None
        self.root_span_id: str | None = None
        self.spans: dict[str, _SpanState] = {}
        self._sum_input = 0
        self._sum_output = 0
        # F3: the distinct (provider, model) pairs seen across every usage report this run, so
        # build_subtree() can tell "one pair throughout" from "several" rather than arbitrarily
        # reporting whichever usage report happened to fold in last.
        self._providers_models: set[tuple[str, str]] = set()

    def map(self, event: ObservationEvent) -> list[Traced]:
        if isinstance(event, RunStarted):
            self.trace_id = event.trace_id
            self.root_span_id = event.root_span_id
        elif isinstance(event, NodeStarted):
            self.spans[event.span_id] = _SpanState(
                event.node_kind, event.detail, datetime.now(UTC), event.parent_span_id
            )
        elif isinstance(event, Log):
            return [Traced(payload=_log_frame(event), span=None)]
        elif isinstance(event, Usage):
            self._fold_usage(event)
        elif isinstance(event, NodeFinished):
            return self._finish(event)
        # RunFinished (and any other case): the run's end is handled by `await task` + the
        # final Completed frame in Url4Executor.execute — nothing to emit here.
        return []

    def _fold_usage(self, event: Usage) -> None:
        self._sum_input += event.input_tokens
        self._sum_output += event.output_tokens
        self._providers_models.add((event.provider, event.model))
        span = self.spans.get(event.span_id) if event.span_id is not None else None
        if span is not None:
            span.usage = (event.provider, event.model, event.input_tokens, event.output_tokens)

    def _finish(self, event: NodeFinished) -> list[Traced]:
        span = self.spans.pop(event.span_id, None)
        if span is None:
            span = _SpanState("", "", datetime.now(UTC), None)
        kind, detail, start, usage, parent_span_id = (
            span.kind,
            span.detail,
            span.start,
            span.usage,
            span.parent_span_id,
        )
        span_data = SpanData(
            name=detail or kind,
            operation=kind,
            provider=usage[0] if usage else None,
            request_model=usage[1] if usage else None,
            response_model=usage[1] if usage else None,
            input_tokens=usage[2] if usage else None,
            output_tokens=usage[3] if usage else None,
            start=start,
            end=datetime.now(UTC),
            status="ok" if event.status == "ok" else "error",
        )
        frames: list[Traced] = [
            Traced(payload=span_data, span=SpanRef(event.span_id, parent_span_id))
        ]
        if usage is not None:
            frames.append(
                Traced(
                    payload=CostUsageData(
                        scope="self",
                        provider=usage[0],
                        model=usage[1],
                        pricing_version="unpriced",
                        usage=TokenUsage(input_tokens=usage[2], output_tokens=usage[3]),
                        cost=CostBreakdown(total_usd=Decimal("0")),
                    ),
                    span=None,
                )
            )
        return frames

    def build_result(self, result_str: str, cap: int) -> ResultData:
        encoded = result_str.encode("utf-8")
        if len(encoded) <= cap:
            return ResultData(body=result_str, media_type=None)
        marker = _TRUNCATION_MARKER.encode("utf-8")
        if len(marker) > cap:
            # F2 tiny-cap edge: the marker itself doesn't fit in `cap` bytes — truncate the marker
            # rather than append it whole and exceed the cap.
            body = marker[:cap].decode("utf-8", errors="ignore")
            return ResultData(body=body, media_type=None)
        kept = encoded[: cap - len(marker)]
        # WHY: errors="ignore" drops a partial multi-byte sequence left dangling by the byte-cap
        # slice above, so the truncated body always decodes cleanly.
        body = kept.decode("utf-8", errors="ignore") + _TRUNCATION_MARKER
        return ResultData(body=body, media_type=None)

    def build_subtree(self) -> CostUsageData:
        # INVARIANT: provider/model are non-nullable on CostUsageData — a run with zero usage
        # reports still emits an all-zero subtree roll-up (lifecycle invariant, §8), so a
        # "none"/"none" sentinel stands in for "no provider was ever observed". F3: when every
        # usage report shares one (provider, model) pair, that pair is reported; when they
        # differ, "mixed"/"mixed" replaces the old arbitrary last-wins choice.
        provider, model = self._subtree_provider_model()
        return CostUsageData(
            scope="subtree",
            provider=provider,
            model=model,
            pricing_version="unpriced",
            usage=TokenUsage(input_tokens=self._sum_input, output_tokens=self._sum_output),
            cost=CostBreakdown(total_usd=Decimal("0")),
        )

    def _subtree_provider_model(self) -> tuple[str, str]:
        if not self._providers_models:
            return "none", "none"
        if len(self._providers_models) == 1:
            return next(iter(self._providers_models))
        return "mixed", "mixed"


def _log_frame(event: Log) -> LogData:
    number, text = _SEVERITY.get(event.severity.upper(), (9, "INFO"))
    return LogData(severity_number=number, severity_text=text, body=event.body)


class Url4Executor:
    """The real url4-engine-backed :class:`~url4_cloud_runner.executor.Executor`.

    ``io`` is the world (deny-by-default :class:`~url4.io.static.StaticIOLayer` for v1); ``None``
    lets the engine fall back to its own default (:class:`~url4.io.http.HttpIOLayer``).

    ``world_aclose``, when given, is awaited exactly once in :meth:`execute`'s teardown — on every
    exit path (success, error, or an early ``aclose()``) — so a per-run world's resources (e.g. the
    aigateway connector's ``httpx.AsyncClient``, plan §5.3) are released when the run ends.
    """

    def __init__(
        self,
        io: IOLayer | None = None,
        *,
        queue_cap: int = 1024,
        result_cap: int = 1_048_576,
        world_aclose: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._io = io
        self._queue_cap = queue_cap
        self._result_cap = result_cap
        self._world_aclose = world_aclose

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        bridge = _Bridge(self._queue_cap)
        state = _RunState()

        async def _drive() -> str:
            try:
                if trace is not None:
                    # publish.run already minted the run-root identity — pass it through so the
                    # engine's own trace_id/root_span_id (and the top node's parent_span_id) agree
                    # with the Runner's, instead of the engine minting its own.
                    return await url4_run(
                        url4,
                        self._io,
                        observer=bridge,
                        trace_id=trace.trace_id,
                        root_span_id=trace.root_span_id,
                    )
                return await url4_run(url4, self._io, observer=bridge)
            finally:
                bridge.close()  # unblock the consumer no matter how the run ends

        task = asyncio.ensure_future(_drive())
        try:
            async for ev in bridge.drain():
                for frame in state.map(ev):
                    yield frame
            # Re-raises the engine's exception UNWRAPPED (code/permanent intact) so it funnels
            # into publish.run's Terminated{failed} path — no Completed is yielded on error.
            result_str = await task
            if bridge.dropped:
                yield Traced(
                    payload=LogData(
                        severity_number=13,
                        severity_text="WARN",
                        body=f"dropped {bridge.dropped} log event(s) (telemetry overflow)",
                    ),
                    span=None,
                )
            yield Completed(
                result=state.build_result(result_str, self._result_cap),
                subtree_cost=state.build_subtree(),
            )
        finally:
            # Structured cancellation: closing this generator early (publish.run stops iterating,
            # or the caller cancels) cancels the in-flight engine run so it stops fetching.
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            elif not task.cancelled():
                # F1: the task may have already finished (with an exception) by the time an early
                # `aclose()` reaches here, racing ahead of the cancellation above — in that case
                # `await task` above never ran, so the task's exception was never retrieved, and
                # asyncio logs "Task exception was never retrieved" when it's later GC'd.
                # `task.exception()` marks it retrieved without changing behavior on the normal
                # path (where `await task` already retrieved it, making this a harmless no-op).
                task.exception()
            await self._aclose_world()

    async def _aclose_world(self) -> None:
        """World teardown (plan §5.3): runs exactly once per :meth:`execute` call, on every exit
        path (success, error, or an early ``aclose()``), alongside the engine-task cleanup above.

        Never re-raise a teardown failure: this runs from ``execute()``'s ``finally``, which may
        already be unwinding the run's real exception (a ParseError/ResolutionError, or
        ``GeneratorExit`` from an early ``aclose()``), and a second exception raised from a
        ``finally`` block replaces whatever was propagating, which would mask that real outcome
        from the caller (``publish.run`` / the test). We log-and-continue rather than swallow
        silently, so a failed per-run world/client teardown (e.g. an httpx pool error) is at least
        observable — an otherwise-invisible resource leak. ``CancelledError`` (a ``BaseException``)
        is not caught.
        """
        if self._world_aclose is None:
            return
        try:
            await self._world_aclose()
        except Exception:  # noqa: BLE001 - teardown failure must not mask the run's real outcome
            _logger.warning("aigateway world teardown failed", exc_info=True)


def deny_by_default_world() -> IOLayer:
    """An empty, locked-down :class:`~url4.io.static.StaticIOLayer` — no ``fetch_map``, no
    ``routes``, no ``holdings`` (§Security deny-by-default). ``__main__.py`` reaches for this
    rather than importing ``url4`` itself, keeping this module the sole C6 import boundary."""
    return StaticIOLayer()


__all__ = ["Url4Executor", "deny_by_default_world"]
