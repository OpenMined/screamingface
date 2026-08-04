"""The run mode's `Executor` port implementation: drives one url4 run over the real engine
(`url4.dag.run`) and bridges its synchronous `url4.observe` callback events into the async
`url4.streaming.protocol` wire frames the run publishes over NATS.

This is one of the three narrow modules (`executor`, `connector`, and `commands`) that may import
the url4 ENGINE — the composition root (`runner.main`) types its world factory against
`World`/`WorldFactory` here without ever importing the engine itself.
`tests/unit/test_url4_executor.py` pins that set over the whole distribution, control plane
included.
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
from typing import cast

from url4.dag import run as url4_run
from url4.io.layer import IOLayer
from url4.io.static import StaticIOLayer
from url4.observe import (
    Log,
    ModelResponse,
    NodeFinished,
    NodeStarted,
    ObservationEvent,
    RunStarted,
    Usage,
)
from url4.streaming.interfaces import Completed, ExecStep, Executor, SpanRef, TraceContext, Traced
from url4.streaming.protocol import (
    SEVERITY_NUMBER,
    CostUsageData,
    LogData,
    ResultData,
    Severity,
    SpanData,
    TokenUsage,
)
from url4.streaming.protocol.taxonomy import CostBreakdown

_logger = logging.getLogger(__name__)

_TRUNCATION_MARKER = "…[truncated]"


class BridgeOverflowError(RuntimeError):
    """Raised by `_Bridge.on_event` when the backlog still exceeds the hard cap after the
    eviction policy has run — eviction only removes a `Log` when one happens to be buffered,
    so a backlog made up of non-Log events can grow unchecked past the soft cap all the way
    to the hard cap, where the streaming consumer is deemed not keeping up with the engine."""


class _Bridge:
    """A bounded async event queue between the engine's synchronous `url4.observe` callback
    and the async streaming loop draining it.

    Buffers up to `maxsize` events; beyond that, an incoming `Log` is dropped outright, while
    an incoming non-Log event instead evicts the oldest buffered `Log` to make room (or, if no
    `Log` is buffered, evicts nothing and the buffer grows toward the hard cap) — since a `Log`
    is the only event kind safe to lose without corrupting the run's span/cost accounting.
    Only past `_HARD_CAP_MULTIPLIER * maxsize` does it give up and raise `BridgeOverflowError`.
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
        """Called synchronously by the engine for every observation event.

        Policy at the soft cap (`maxsize`): a `Log` is dropped outright (counted in
        `dropped`); anything else evicts the oldest buffered `Log` to make room, since a
        `Log` is the only event kind safe to lose without corrupting the run's span/cost
        accounting. Only once the backlog still exceeds the hard cap after that eviction does
        this raise `BridgeOverflowError`.
        """
        # INVARIANT: _hard_cap > _max (_HARD_CAP_MULTIPLIER > 1) gives the buffer headroom to
        # grow past the soft cap before it hits the hard cap — NOT a guarantee that a Log is
        # available to evict. A backlog with no buffered Log at all is exactly the state that
        # runs out that headroom and raises BridgeOverflowError.
        if len(self._buf) >= self._max:
            if isinstance(event, Log):
                self._dropped += 1
                return
            self._evict_oldest_log()
        if len(self._buf) >= self._hard_cap:
            raise BridgeOverflowError(
                f"event backlog exceeded the hard cap ({self._hard_cap} events, "
                f"{self._dropped} Log(s) already dropped) — the consumer is not keeping up"
            )
        self._buf.append(event)
        self._wake.set()

    def _evict_oldest_log(self) -> None:
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
    """An in-flight span's accumulated fields, held between its `NodeStarted` and matching
    `NodeFinished` events so `_RunState._finish` can build the wire-protocol `SpanData`."""

    kind: str
    detail: str
    start: datetime
    parent_span_id: str | None
    usage: tuple[str, str, int, int] | None = field(default=None)
    # Held beside `usage` rather than widening that tuple: it is the only one of these fields
    # that can legitimately be absent (a provider need not echo a model), so a 5th positional
    # slot would read as "unknown" and "not reported" interchangeably.
    response_model: str | None = field(default=None)
    # INVARIANT: a LIST, accumulated — one span can make several model calls (the web-tools loop
    # is the normal case), and each round trip's reason is separately auditable.
    #
    # AIDEV-NOTE: empty here covers TWO cases that `_finish` deliberately collapses to one on the
    # wire — a node that called no model, and a call whose provider omitted `finish_reason`. They
    # are NOT distinguishable downstream. Nothing consumes the difference today; if something ever
    # needs it, count the folded events here rather than inferring it from this list.
    finish_reasons: list[str] = field(default_factory=list)
    refusal: str | None = field(default=None)


class _RunState:
    """Accumulates one run's `url4.observe` events into wire-protocol span and cost frames.

    Tracks in-flight spans by `span_id` (opened on `NodeStarted`, closed on `NodeFinished`)
    and folds every `Usage` event into both the owning span's usage and the run-wide subtree
    totals returned by `build_subtree`.
    """

    def __init__(self) -> None:
        self.trace_id: str | None = None
        self.root_span_id: str | None = None
        self.spans: dict[str, _SpanState] = {}
        self._sum_input = 0
        self._sum_output = 0
        self._providers_models: set[tuple[str, str]] = set()

    def map(self, event: ObservationEvent) -> list[Traced]:
        """Fold one observation event into run state, returning the wire frames it produces.

        Dispatches on event type: `RunStarted` records the trace/root ids (no frame);
        `NodeStarted` opens a span (no frame); `Log` maps straight to a `Traced` log frame;
        `Usage` folds token counts into the owning span and the run totals (no frame);
        `NodeFinished` closes the span and returns its `SpanData` frame, plus a `CostUsageData`
        frame when the span carried usage. Any other event type produces nothing.
        """
        if isinstance(event, RunStarted):
            self.trace_id = event.trace_id
            self.root_span_id = event.root_span_id
        elif isinstance(event, NodeStarted):
            self.spans[event.span_id] = _SpanState(
                event.node_kind, event.detail, datetime.now(UTC), event.parent_span_id
            )
        elif isinstance(event, Log):
            # The engine attributes each log line to the span that emitted it; carry that through
            # so a consumer can tell WHICH node logged. A span-less line (logged outside any
            # node) legitimately has none and falls back to the run root.
            return [Traced(payload=_log_frame(event), span=self._span_ref(event.span_id))]
        elif isinstance(event, Usage):
            self._fold_usage(event)
        elif isinstance(event, ModelResponse):
            self._fold_response(event)
        elif isinstance(event, NodeFinished):
            return self._finish(event)
        return []

    def _span_ref(self, span_id: str | None) -> SpanRef | None:
        """A `SpanRef` for a live span, or None when the frame belongs to the run itself.

        A span id the run has never seen (or has already finished) resolves to None rather than
        being fabricated: publishing under an id no span frame ever carried would be worse than
        falling back to the root, because a consumer cannot tell the two apart.
        """
        if span_id is None:
            return None
        span = self.spans.get(span_id)
        if span is None:
            return None
        return SpanRef(span_id, span.parent_span_id)

    def _fold_response(self, event: ModelResponse) -> None:
        """Accumulate one model round trip's outcome onto the span that made the call.

        Mirrors `_fold_usage`'s guard and its accumulate-don't-assign rule: an event for a span
        this run never opened is dropped rather than fabricating one, and several calls on the
        same span each keep their own entry.
        """
        span = self.spans.get(event.span_id) if event.span_id is not None else None
        if span is None:
            return
        if event.finish_reason is not None:
            span.finish_reasons.append(event.finish_reason)
        if event.refusal is not None:
            # Last refusal wins: for a multi-call turn the final one is the turn's outcome.
            span.refusal = event.refusal

    def _fold_usage(self, event: Usage) -> None:
        self._sum_input += event.input_tokens
        self._sum_output += event.output_tokens
        self._providers_models.add((event.provider, event.model))
        span = self.spans.get(event.span_id) if event.span_id is not None else None
        if span is None:
            return
        # INVARIANT: a span ACCUMULATES its usage, exactly as the subtree totals above do — one
        # node can emit several `Usage` events. The web-tools tool loop is the normal case: every
        # aigateway round trip reports its own usage against the SAME span, so assigning here
        # (as this once did) kept only the final round trip and silently dropped every earlier
        # one from both the span frame and its `scope="self"` cost frame, while `subtree` stayed
        # correct — per-node cost that under-reports against a run total that does not.
        prior_in, prior_out = (span.usage[2], span.usage[3]) if span.usage else (0, 0)
        span.usage = (
            event.provider,
            event.model,
            prior_in + event.input_tokens,
            prior_out + event.output_tokens,
        )
        # Last writer wins, and a silent event never erases a known one: across the tool loop's
        # round trips every response names the same model, so the only way these differ is a
        # provider that stopped reporting mid-loop.
        span.response_model = event.response_model or span.response_model

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
            # INVARIANT: left absent when the provider did not name a model. It previously
            # repeated `request_model`, which made an alias silently resolving to a different
            # snapshot — the one thing this field exists to reveal — indistinguishable from
            # the provider serving exactly what was asked for.
            response_model=span.response_model,
            input_tokens=usage[2] if usage else None,
            output_tokens=usage[3] if usage else None,
            # Empty -> None so the attribute is simply ABSENT rather than an empty list, matching
            # how OTel treats `gen_ai.*` attributes. This collapses "no model call" and "a call
            # that reported no reason" into the same wire shape — intended, not an oversight.
            finish_reasons=span.finish_reasons or None,
            refusal=span.refusal,
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
                    # INVARIANT: the self-scoped cost carries the SAME span as the span frame it
                    # accompanies. Without it every `scope="self"` frame in a run is published
                    # under the run root and is therefore indistinguishable from every other —
                    # nobody can tell which node spent the tokens, and self cannot be reconciled
                    # against subtree per node, which is the whole point of emitting both.
                    span=SpanRef(event.span_id, parent_span_id),
                )
            )
        return frames

    def build_result(self, result_str: str, cap: int) -> ResultData:
        """Build the final `ResultData`, truncating to `cap` UTF-8 bytes when needed.

        A truncated body keeps as much of the original text as fits alongside
        `_TRUNCATION_MARKER`, cutting on a byte boundary (`errors="ignore"` drops any partial
        trailing character rather than raising). If even the marker alone doesn't fit in
        `cap`, the body is the marker itself, truncated.
        """
        encoded = result_str.encode("utf-8")
        if len(encoded) <= cap:
            return ResultData(body=result_str, media_type=None)
        marker = _TRUNCATION_MARKER.encode("utf-8")
        if len(marker) > cap:
            body = marker[:cap].decode("utf-8", errors="ignore")
            return ResultData(body=body, media_type=None)
        kept = encoded[: cap - len(marker)]
        body = kept.decode("utf-8", errors="ignore") + _TRUNCATION_MARKER
        return ResultData(body=body, media_type=None)

    def build_subtree(self) -> CostUsageData:
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
    # The engine's severity is a free string; anything the protocol does not name maps to INFO.
    severity = cast(Severity, event.severity.upper())
    return LogData.at(severity if severity in SEVERITY_NUMBER else "INFO", event.body)


World = tuple[IOLayer, Callable[[], Awaitable[None]] | None]
"""A resolved world: its io layer plus the teardown that owns whatever it allocated.

Exported so the composition root can type its factory WITHOUT importing the engine — only
this module and `connector` may (pinned by
``test_only_url4_executor_module_imports_url4``).
"""

WorldFactory = Callable[[], Awaitable[World]]


class Url4Executor(Executor):
    """The `Executor` port implementation that drives one url4 run against the real engine.

    Resolves its `World` (an `IOLayer` plus teardown) lazily on first `execute`, runs
    `url4.dag.run` against it with a `_Bridge` as observer, and maps the resulting
    `url4.observe` events through `_RunState` into the `ExecStep` frames it yields.
    """

    def __init__(
        self,
        io: IOLayer | None = None,
        *,
        queue_cap: int = 1024,
        result_cap: int = 1_048_576,
        world_aclose: Callable[[], Awaitable[None]] | None = None,
        world_factory: WorldFactory | None = None,
    ) -> None:
        self._io = io
        self._queue_cap = queue_cap
        self._result_cap = result_cap
        self._world_aclose = world_aclose
        self._world_factory = world_factory

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        """Run `url4` to completion, yielding `ExecStep` frames as observation events arrive.

        Runs the engine in a separate task (`_drive`) while draining its events through the
        `_Bridge` on this task, so a slow consumer never blocks the engine's synchronous
        observer callback. On exit — including early return by the caller not exhausting the
        iterator — any still-running driving task is cancelled and awaited, and an already
        finished task's exception (if not itself a cancellation) is retrieved so it isn't
        reported as "never retrieved". The world is always closed via `_aclose_world`, even
        when the run failed or was cancelled.
        """
        # INVARIANT: the world is resolved HERE, not in the composition root. Anything raised
        # before `lifecycle.run` publishes its first frame is invisible — no NATS connection,
        # no `ensure_stream`, so an attached client sees heartbeats forever and never a
        # Terminated. Resolving inside `execute` puts config and connect failures inside
        # `run`'s try, where they become Terminated(status="failed") with a real error code.
        await self._resolve_world()
        bridge = _Bridge(self._queue_cap)
        state = _RunState()

        async def _drive() -> str:
            try:
                if trace is not None:
                    return await url4_run(
                        url4,
                        self._io,
                        observer=bridge,
                        trace_id=trace.trace_id,
                        root_span_id=trace.root_span_id,
                    )
                return await url4_run(url4, self._io, observer=bridge)
            finally:
                bridge.close()

        task = asyncio.ensure_future(_drive())
        try:
            async for ev in bridge.drain():
                for frame in state.map(ev):
                    yield frame
            result_str = await task
            if bridge.dropped:
                yield Traced(
                    payload=LogData.at(
                        "WARN", f"dropped {bridge.dropped} log event(s) (telemetry overflow)"
                    ),
                    span=None,
                )
            yield Completed(
                result=state.build_result(result_str, self._result_cap),
                subtree_cost=state.build_subtree(),
            )
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            elif not task.cancelled():
                task.exception()
            await self._aclose_world()

    async def _resolve_world(self) -> None:
        """Build the world on first execute. Idempotent; a failure leaves nothing to close.

        The factory owns cleanup of anything it allocated before failing, so there is no
        half-built world to tear down here.
        """
        if self._world_factory is None or self._io is not None:
            return
        self._io, self._world_aclose = await self._world_factory()

    async def _aclose_world(self) -> None:
        if self._world_aclose is None:
            return
        try:
            await self._world_aclose()
        except Exception:  # noqa: BLE001 - teardown failure must not mask the run's real outcome
            _logger.warning("aigateway world teardown failed", exc_info=True)


def deny_by_default_world() -> IOLayer:
    return StaticIOLayer()


__all__ = ["Url4Executor", "deny_by_default_world"]
