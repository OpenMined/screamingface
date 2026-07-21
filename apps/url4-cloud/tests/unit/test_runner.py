"""OME-520 — the Runner Job entrypoint: lifecycle publication + failure terminal + env parsing."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from url4_cloud_nats import InMemoryBus
from url4_cloud_protocol import (
    CostUsageData,
    CostUsageEvent,
    LogData,
    OutboundFrame,
    ResultData,
    SpanData,
    TerminatedEvent,
    TokenUsage,
)
from url4_cloud_protocol.taxonomy import CostBreakdown
from url4_cloud_runner import Completed, ExecStep, MockExecutor, run
from url4_cloud_runner.__main__ import RunnerConfigError, params_from_env

TOPIC = "cap-topic"
EXPR = "(@)!'hi'"

_LIFECYCLE = [
    "ai.url4.started",
    "ai.url4.log",
    "ai.url4.span",
    "ai.url4.cost.usage",
    "ai.url4.cost.usage",
    "ai.url4.result",
    "ai.url4.terminated",
]


class RecordingBus:
    """A ``Bus`` double that captures published events *before* the wire codec re-sequences them."""

    def __init__(self) -> None:
        self.published: list[OutboundFrame] = []
        self.ensured: list[str] = []

    async def ensure_stream(self, topic: str) -> None:
        self.ensured.append(topic)

    async def publish(self, topic: str, event: OutboundFrame) -> None:
        self.published.append(event)

    async def subscribe(
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]:
        for event in self.published:
            yield event

    async def purge(self, topic: str) -> None:
        self.published.clear()


class _RaisingExecutor:
    """Yields one log, then raises — drives the failure terminal path."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def execute(self, url4: str) -> AsyncIterator[ExecStep]:
        yield LogData(severity_number=9, severity_text="INFO", body="starting")
        raise self._exc


class _NoCompletionExecutor:
    """Streams telemetry but never yields a terminal ``Completed`` — a malformed executor."""

    async def execute(self, url4: str) -> AsyncIterator[ExecStep]:
        yield LogData(severity_number=9, severity_text="INFO", body="only-telemetry")


class _FakeUrl4Error(Exception):
    """Duck-types url4 ``Url4Error`` — carries ``code`` + ``permanent`` without importing url4."""

    def __init__(self, message: str, *, code: str, permanent: bool) -> None:
        super().__init__(message)
        self.code = code
        self.permanent = permanent


async def _take(bus: InMemoryBus, topic: str, n: int) -> list[OutboundFrame]:
    out: list[OutboundFrame] = []

    async def _run() -> None:
        async for event in bus.subscribe(topic, from_sequence=1):
            out.append(event)
            if len(out) >= n:
                break

    await asyncio.wait_for(_run(), timeout=2.0)
    return out


@pytest.mark.asyncio
async def test_success_publishes_full_lifecycle_in_order() -> None:
    bus = RecordingBus()
    await run(bus, MockExecutor(), TOPIC, EXPR)

    assert [e.type for e in bus.published] == _LIFECYCLE
    assert bus.ensured == [TOPIC]


@pytest.mark.asyncio
async def test_success_sets_monotonic_sequence_and_envelope() -> None:
    bus = RecordingBus()
    await run(bus, MockExecutor(), TOPIC, EXPR)

    seqs = [int(e.sequence) for e in bus.published if e.sequence is not None]
    assert len(seqs) == len(bus.published)
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    for event in bus.published:
        assert event.id and len(event.id) == 32  # uuid4().hex
        assert event.source == f"/trace/{TOPIC}/node/root"
        assert event.subject == TOPIC
        assert event.time is not None
        assert event.sequencetype == "Integer"


@pytest.mark.asyncio
async def test_subtree_cost_precedes_result_and_self_cost_streamed() -> None:
    bus = RecordingBus()
    await run(bus, MockExecutor(), TOPIC, EXPR)

    types = [e.type for e in bus.published]
    result_idx = types.index("ai.url4.result")
    before_result = bus.published[result_idx - 1]
    assert isinstance(before_result, CostUsageEvent)
    assert before_result.data.scope == "subtree"

    first_cost = bus.published[types.index("ai.url4.cost.usage")]
    assert isinstance(first_cost, CostUsageEvent)
    assert first_cost.data.scope == "self"

    term = bus.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "succeeded"
    assert term.data.error is None


@pytest.mark.asyncio
async def test_failure_terminates_with_mapped_error() -> None:
    bus = RecordingBus()
    exc = _FakeUrl4Error("boom", code="resolution_failed", permanent=False)
    await run(bus, _RaisingExecutor(exc), TOPIC, EXPR)

    assert [e.type for e in bus.published] == [
        "ai.url4.started",
        "ai.url4.log",
        "ai.url4.terminated",
    ]
    term = bus.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "failed"
    assert term.data.error is not None
    assert term.data.error.code == "resolution_failed"
    assert term.data.error.permanent is False
    assert "boom" in term.data.error.message


@pytest.mark.asyncio
async def test_failure_generic_exception_defaults_to_internal_permanent() -> None:
    bus = RecordingBus()
    await run(bus, _RaisingExecutor(ValueError("nope")), TOPIC, EXPR)

    term = bus.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "failed"
    assert term.data.error is not None
    assert term.data.error.code == "internal_error"
    assert term.data.error.permanent is True
    assert "nope" in term.data.error.message


@pytest.mark.asyncio
async def test_executor_without_completed_terminates_failed() -> None:
    bus = RecordingBus()
    await run(bus, _NoCompletionExecutor(), TOPIC, EXPR)

    term = bus.published[-1]
    assert isinstance(term, TerminatedEvent)
    assert term.data.status == "failed"
    assert term.data.error is not None


@pytest.mark.asyncio
async def test_lifecycle_round_trips_through_in_memory_bus() -> None:
    bus = InMemoryBus()
    await run(bus, MockExecutor(), TOPIC, EXPR)

    got = await _take(bus, TOPIC, len(_LIFECYCLE))
    assert [int(e.sequence) for e in got if e.sequence is not None] == [1, 2, 3, 4, 5, 6, 7]
    assert [e.type for e in got] == _LIFECYCLE
    last = got[-1]
    assert isinstance(last, TerminatedEvent)
    assert last.data.status == "succeeded"


@pytest.mark.asyncio
async def test_custom_executor_streams_are_wrapped_with_envelopes() -> None:
    # WHY: a hand-built executor (not the mock) proves the port is the real seam.
    class _OneSpanExecutor:
        async def execute(self, url4: str) -> AsyncIterator[ExecStep]:
            yield SpanData(name="chat", operation="chat", start=datetime.now(UTC))
            yield Completed(
                result=ResultData(body="ok"),
                subtree_cost=CostUsageData(
                    scope="self",  # deliberately wrong — run() must force "subtree"
                    provider="anthropic",
                    model="claude-opus-4-8",
                    pricing_version="2026-07-01",
                    usage=TokenUsage(),
                    cost=CostBreakdown(total_usd=Decimal("0")),
                ),
            )

    bus = RecordingBus()
    await run(bus, _OneSpanExecutor(), TOPIC, EXPR)

    types = [e.type for e in bus.published]
    assert types == [
        "ai.url4.started",
        "ai.url4.span",
        "ai.url4.cost.usage",
        "ai.url4.result",
        "ai.url4.terminated",
    ]
    subtree = bus.published[types.index("ai.url4.result") - 1]
    assert isinstance(subtree, CostUsageEvent)
    # INVARIANT: the pre-result roll-up is always scope="subtree", regardless of executor input.
    assert subtree.data.scope == "subtree"


def test_params_from_env_reads_topic_expr_and_nats() -> None:
    params = params_from_env(
        {
            "URL4_CLOUD_TOPIC": "cap",
            "URL4_CLOUD_EXPRESSION": EXPR,
            "URL4_CLOUD_NATS_URL": "nats://node:4222",
        }
    )
    assert params.topic == "cap"
    assert params.url4 == EXPR
    assert params.nats_url == "nats://node:4222"


def test_params_from_env_defaults_nats_url() -> None:
    params = params_from_env({"URL4_CLOUD_TOPIC": "cap", "URL4_CLOUD_EXPRESSION": EXPR})
    assert params.nats_url == "nats://localhost:4222"


def test_params_from_env_missing_required_raises() -> None:
    with pytest.raises(RunnerConfigError):
        params_from_env({"URL4_CLOUD_EXPRESSION": EXPR})
