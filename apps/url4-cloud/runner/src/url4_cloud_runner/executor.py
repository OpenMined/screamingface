"""The ``Executor`` port — the url4 execution seam the Runner publishes from (spec §1.1, OME-446).

The Runner (:mod:`url4_cloud_runner.publish`) owns the CloudEvents envelope (id / source / sequence
/ time) and the lifecycle framing; the ``Executor`` owns *what happened* — it streams telemetry
payloads "as available", then yields exactly one terminal :class:`Completed` carrying the result and
the subtree cost roll-up. PEP 525 forbids a value-returning async generator, so the outcome rides as
the final yielded item rather than a ``return``.

The production adapter implementing this port is
:class:`~url4_cloud_runner.url4_executor.Url4Executor` (the OME-446 engine seam), wired into every
real execution path — k8s/docker pods via :func:`url4_cloud_runner.__main__.build_executor`, local
mode via :func:`url4_cloud.app.make_local_app`.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from url4_streaming_protocol import (
    CostUsageData,
    LogData,
    ResultData,
    SpanData,
)

# Telemetry the executor streams "as available" — each wrapped into its CloudEvent by the Runner.
Telemetry = LogData | SpanData | CostUsageData


@dataclass(frozen=True)
class TraceContext:
    """The run-root trace identity :mod:`~url4_cloud_runner.publish` establishes (before the first
    publish) and passes INTO :meth:`Executor.execute` — the trace_id/root_span_id every frame this
    run publishes is ultimately stamped against (spec traceparent PRD §3.2.2)."""

    trace_id: str
    root_span_id: str


@dataclass(frozen=True)
class SpanRef:
    """Per-span identity an adapter emits OUT alongside a span's :data:`Telemetry` payload — the
    engine's own span_id/parent_span_id for that node evaluation."""

    span_id: str
    parent_span_id: str | None


@dataclass(frozen=True)
class Traced:
    """A :data:`Telemetry` payload plus its span identity — ``span`` is ``None`` for non-span
    frames (``Log``, ``CostUsage{self}``), populated for span frames so the Runner can stamp the
    right ``traceparent``/``tracestate`` per THE STAMPING RULES."""

    payload: Telemetry
    span: SpanRef | None


@dataclass(frozen=True)
class Completed:
    """The terminal outcome of a url4 execution: the result body + the subtree cost roll-up.

    Carrying both together makes the spec §8 ordering invariant ("``CostUsage{subtree}`` emitted
    before ``Result``") true by construction — the Runner emits them back-to-back from this value.
    """

    result: ResultData
    subtree_cost: CostUsageData


# One step of an execution stream: a telemetry payload (bare, or with span identity), or the
# single terminal ``Completed``.
ExecStep = Telemetry | Traced | Completed


class Executor(Protocol):
    """Runs a url4 expression, streaming :data:`Telemetry`/:class:`Traced` then one terminal
    :class:`Completed`.

    ``trace``, when given, is the run-root context (spec traceparent PRD) the adapter should thread
    into its underlying engine so span identity agrees with the Runner's own root; an adapter that
    ignores it (a bare-``Telemetry`` executor) still works — the Runner tolerates bare
    ``Telemetry``.
    """

    def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]: ...
