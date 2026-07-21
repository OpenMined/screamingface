"""``run`` — the Runner's execute-and-publish orchestration (spec §1.1; docs/protocol.md §4).

Publishes the CloudEvents lifecycle to the injected :class:`~url4_cloud_nats.Bus`:
``Started`` → (``Log``/``Span``/``CostUsage{self}`` as available) → ``CostUsage{subtree}`` →
``Result`` → ``Terminated{succeeded}``; any exception funnels to ``Terminated{failed}`` with an
:class:`~url4_cloud_protocol.ErrorInfo`. Both the :class:`~url4_cloud_runner.executor.Executor` and
the ``Bus`` are injected so tests drive a stub executor + in-memory bus (no url4/network — INFRA).
"""

from datetime import UTC, datetime
from typing import Literal, TypedDict
from uuid import uuid4

from url4_cloud_nats import Bus
from url4_cloud_protocol import (
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
from url4_cloud_runner.executor import Completed, Executor, Telemetry


class _Envelope(TypedDict):
    """The CloudEvents attributes the Runner assigns per event (docs/protocol.md §1, §3, §6)."""

    id: str
    source: str
    subject: str
    time: datetime
    sequence: str
    sequencetype: Literal["Integer"]


class _IncompleteExecution(Exception):
    """The executor's stream ended without a terminal ``Completed`` — a malformed executor."""


class _Sequencer:
    """Stamps each event with a fresh envelope: uuid4 id, node source, monotonic string sequence."""

    def __init__(self, topic: str, node: str) -> None:
        # INVARIANT: source addresses the emitting node (docs/protocol.md §1); subject == the run.
        self._source = f"/trace/{topic}/node/{node}"
        self._subject = topic
        self._n = 0

    def next(self) -> _Envelope:
        self._n += 1
        return _Envelope(
            id=uuid4().hex,
            source=self._source,
            subject=self._subject,
            time=datetime.now(UTC),
            sequence=str(self._n),
            sequencetype="Integer",
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


async def run(bus: Bus, executor: Executor, topic: str, url4: str, *, node: str = "root") -> None:
    """Execute ``url4`` via ``executor`` and publish its CloudEvents lifecycle to ``bus``."""
    # WHY: the Runner is the producer; ensure the per-topic stream exists before the first publish
    # (idempotent; NatsBus.publish does not auto-create the stream).
    await bus.ensure_stream(topic)
    seq = _Sequencer(topic, node)
    try:
        await bus.publish(topic, StartedEvent(**seq.next(), data=StartedData(url4=url4)))
        completed: Completed | None = None
        async for step in executor.execute(url4):
            if isinstance(step, Completed):
                completed = step
                break
            await bus.publish(topic, _wrap_telemetry(seq.next(), step))
        if completed is None:
            raise _IncompleteExecution("executor produced no Completed outcome")
        # INVARIANT: the pre-result roll-up is always scope="subtree" (spec §8), whatever came in.
        subtree = completed.subtree_cost.model_copy(update={"scope": "subtree"})
        await bus.publish(topic, CostUsageEvent(**seq.next(), data=subtree))
        await bus.publish(topic, ResultEvent(**seq.next(), data=completed.result))
        await bus.publish(
            topic, TerminatedEvent(**seq.next(), data=TerminatedData(status="succeeded"))
        )
    except Exception as exc:
        await bus.publish(
            topic,
            TerminatedEvent(
                **seq.next(), data=TerminatedData(status="failed", error=_error_info(exc))
            ),
        )
