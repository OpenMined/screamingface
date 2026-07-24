"""``InProcessJobRunner``: the ``JobRunner`` port over an in-process ``asyncio.Task`` (local-mode
PRD §7 tests 2-3, docs/plans/url4-cloud-integration/prd/local-mode.md).

Engine-independent: drives ``publish.run`` with the ``MockExecutor`` test double (``_fakes``)
and hand-rolled test doubles over an :class:`~url4_cloud_nats.InMemoryBus` — no ``url4`` import.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest
from _fakes import MockExecutor

from url4_cloud.jobs import JobAlreadyExists, JobRunner, job_name
from url4_cloud.jobs.inprocess import InProcessJobRunner
from url4_cloud_nats import InMemoryBus
from url4_cloud_runner import ExecStep, TraceContext
from url4_streaming_protocol import OutboundFrame, TerminatedEvent

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


class _BlockingExecutor:
    """Yields nothing; blocks on an ``Event`` that's never set — simulates a pending fetch.

    ``resumed`` proves whether execution ever got past the block: it must stay ``False`` when the
    owning task is cancelled while awaiting the gate.
    """

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.resumed = False
        self._gate = asyncio.Event()

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        self.started.set()
        await self._gate.wait()
        self.resumed = True
        if False:  # pragma: no cover - never reached; keeps this an async generator function
            yield


class _FailingExecutor:
    """Raises inside ``execute()`` before any telemetry — drives ``publish.run``'s failure path."""

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        raise ValueError("boom")
        yield  # pragma: no cover - never reached; keeps this an async generator function


async def _take(
    bus: InMemoryBus, topic: str, n: int, from_sequence: int | None = None
) -> list[OutboundFrame]:
    out: list[OutboundFrame] = []

    async def _run() -> None:
        async for event in bus.subscribe(topic, from_sequence):
            out.append(event)
            if len(out) >= n:
                break

    await asyncio.wait_for(_run(), timeout=2.0)
    return out


def test_runner_satisfies_the_port() -> None:
    runner: JobRunner = InProcessJobRunner(InMemoryBus(), MockExecutor)
    assert isinstance(runner, JobRunner)


@pytest.mark.asyncio
async def test_schedule_runs_publish_on_a_task_keyed_by_job_name() -> None:
    bus = InMemoryBus()
    runner = InProcessJobRunner(bus, MockExecutor)

    name = runner.schedule(TOPIC, EXPR, deadline_s=60)

    assert name == job_name(TOPIC)
    got = await _take(bus, TOPIC, len(_LIFECYCLE))
    assert [e.type for e in got] == _LIFECYCLE
    last = got[-1]
    assert isinstance(last, TerminatedEvent)
    assert last.data.status == "succeeded"


@pytest.mark.asyncio
async def test_schedule_accepts_credential_and_profile_kwargs_for_protocol_conformance() -> None:
    # Batch 3: inprocess accepts credential/profile (Protocol conformance) but does nothing with
    # them yet — local per-run world wiring is Batch 4. The run still succeeds normally.
    bus = InMemoryBus()
    runner = InProcessJobRunner(bus, MockExecutor)

    name = runner.schedule(TOPIC, EXPR, deadline_s=60, credential="tok", profile="p")

    assert name == job_name(TOPIC)
    got = await _take(bus, TOPIC, len(_LIFECYCLE))
    assert [e.type for e in got] == _LIFECYCLE


@pytest.mark.asyncio
async def test_duplicate_schedule_while_running_raises_job_already_exists() -> None:
    bus = InMemoryBus()
    blocking = _BlockingExecutor()
    runner = InProcessJobRunner(bus, lambda: blocking)
    runner.schedule(TOPIC, EXPR, deadline_s=60)
    await blocking.started.wait()

    with pytest.raises(JobAlreadyExists):
        runner.schedule(TOPIC, EXPR, deadline_s=60)

    await runner.aclose()


@pytest.mark.asyncio
async def test_schedule_after_completion_is_allowed() -> None:
    # NOTE: this deliberately diverges from K8sJobRunner, where the Job object persists (and
    # re-blocks a schedule) until an explicit stop/delete. In-process, a completed task frees its
    # slot immediately (Deliverable 1's `.done()` guard) — see the report.
    bus = InMemoryBus()
    runner = InProcessJobRunner(bus, MockExecutor)
    runner.schedule(TOPIC, EXPR, deadline_s=60)
    await _take(bus, TOPIC, len(_LIFECYCLE))
    assert runner.exists(TOPIC) is False

    name = runner.schedule(TOPIC, EXPR, deadline_s=60)

    assert name == job_name(TOPIC)
    got = await _take(bus, TOPIC, len(_LIFECYCLE), from_sequence=len(_LIFECYCLE) + 1)
    assert [e.type for e in got] == _LIFECYCLE


@pytest.mark.asyncio
async def test_finished_task_history_is_bounded_and_evicted_oldest_first() -> None:
    # Regression: `_tasks` used to retain one entry per distinct topic for the process lifetime.
    # With max_history=1, a second completed run must evict the first's entry so status() falls
    # back to not_found instead of growing unbounded — mirrors K8sJobRunner's substrate TTL,
    # just enforced in-process.
    bus = InMemoryBus()
    runner = InProcessJobRunner(bus, MockExecutor, max_history=1)

    runner.schedule("topic-a", EXPR, deadline_s=60)
    await _take(bus, "topic-a", len(_LIFECYCLE))
    assert runner.status("topic-a") == "succeeded"
    assert len(runner._tasks) == 1

    runner.schedule("topic-b", EXPR, deadline_s=60)
    await _take(bus, "topic-b", len(_LIFECYCLE))

    assert len(runner._tasks) == 1
    assert runner.status("topic-a") == "not_found"
    assert runner.status("topic-b") == "succeeded"


@pytest.mark.asyncio
async def test_history_prune_never_evicts_a_still_running_task() -> None:
    # First schedule() gets the never-completing executor; every later one gets MockExecutor —
    # so topic-running stays in-flight while topic-b/topic-c complete and trigger prunes.
    bus = InMemoryBus()
    blocking = _BlockingExecutor()
    executors = iter([blocking, MockExecutor(), MockExecutor()])
    runner = InProcessJobRunner(bus, lambda: next(executors), max_history=1)

    runner.schedule("topic-running", EXPR, deadline_s=60)
    await blocking.started.wait()
    runner.schedule("topic-b", EXPR, deadline_s=60)
    await _take(bus, "topic-b", len(_LIFECYCLE))
    runner.schedule("topic-c", EXPR, deadline_s=60)
    await _take(bus, "topic-c", len(_LIFECYCLE))

    # The still-running task's slot survives every prune — only DONE entries are evicted.
    assert runner.exists("topic-running") is True

    await runner.aclose()


@pytest.mark.asyncio
async def test_exists_reflects_the_running_task_only() -> None:
    bus = InMemoryBus()
    runner = InProcessJobRunner(bus, MockExecutor)
    assert runner.exists(TOPIC) is False

    runner.schedule(TOPIC, EXPR, deadline_s=60)
    assert runner.exists(TOPIC) is True

    await _take(bus, TOPIC, len(_LIFECYCLE))
    assert runner.exists(TOPIC) is False


@pytest.mark.asyncio
async def test_stop_cancels_the_in_flight_task_and_the_blocking_fetch_never_resolves() -> None:
    bus = InMemoryBus()
    blocking = _BlockingExecutor()
    runner = InProcessJobRunner(bus, lambda: blocking)
    runner.schedule(TOPIC, EXPR, deadline_s=60)
    await blocking.started.wait()

    runner.stop(TOPIC)
    await asyncio.sleep(0.05)  # let the cancellation land

    assert runner.status(TOPIC) == "stopped"
    assert blocking.resumed is False


@pytest.mark.asyncio
async def test_stop_is_idempotent_on_an_unknown_topic() -> None:
    runner = InProcessJobRunner(InMemoryBus(), MockExecutor)
    runner.stop(TOPIC)  # no schedule ever happened — no error


@pytest.mark.asyncio
async def test_status_transitions_not_found_running_succeeded() -> None:
    bus = InMemoryBus()
    runner = InProcessJobRunner(bus, MockExecutor)
    assert runner.status(TOPIC) == "not_found"

    runner.schedule(TOPIC, EXPR, deadline_s=60)
    assert runner.status(TOPIC) == "running"

    await _take(bus, TOPIC, len(_LIFECYCLE))
    assert runner.status(TOPIC) == "succeeded"


@pytest.mark.asyncio
async def test_failing_executor_run_fails_cleanly_but_the_task_succeeds() -> None:
    # publish.run's `except Exception` catches the executor's failure and publishes
    # Terminated{failed} instead of propagating — so the in-process TASK completes normally.
    # Task-level "failed" is reserved for a crash in publish.run itself (e.g. bus.ensure_stream
    # raising before the try block), not for a run that fails-cleanly through the lifecycle.
    bus = InMemoryBus()
    runner = InProcessJobRunner(bus, _FailingExecutor)

    runner.schedule(TOPIC, EXPR, deadline_s=60)
    got = await _take(bus, TOPIC, 2)

    assert [e.type for e in got] == ["ai.url4.started", "ai.url4.terminated"]
    last = got[-1]
    assert isinstance(last, TerminatedEvent)
    assert last.data.status == "failed"
    assert runner.status(TOPIC) == "succeeded"


@pytest.mark.asyncio
async def test_aclose_cancels_in_flight_blocking_run_and_returns_cleanly() -> None:
    bus = InMemoryBus()
    blocking = _BlockingExecutor()
    runner = InProcessJobRunner(bus, lambda: blocking)
    runner.schedule(TOPIC, EXPR, deadline_s=60)
    await blocking.started.wait()

    await runner.aclose()

    assert runner.status(TOPIC) == "stopped"
    assert blocking.resumed is False


@pytest.mark.asyncio
async def test_aclose_with_no_tasks_returns_cleanly() -> None:
    runner = InProcessJobRunner(InMemoryBus(), MockExecutor)
    await runner.aclose()
