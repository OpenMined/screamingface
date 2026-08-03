"""A Runner Job that is SIGTERM'd still publishes its terminal frame.

FEATURE: cancelling an in-flight run (OME-315).
STORY: as a user who cancelled a run, I need the stream to END, so my client stops waiting and
can tell "cancelled" apart from "still running".

INVARIANT under test: the frame must be observed on the STREAM. Asserting that a handler was
installed would only prove the code ran — the defect these tests pin returned a healthy-looking
process and an eternally silent topic.
"""

import asyncio
import os
import signal
from collections.abc import AsyncIterator

import pytest
from _fakes import MockExecutor

from url4.streaming.interfaces import ExecStep, Executor, TraceContext
from url4.streaming.lifecycle import run
from url4.streaming.protocol import LogData, OutboundFrame, TerminatedEvent
from url4_cloud.runner.main import cancel_on_signal
from url4_cloud.testing import InMemoryEventStream

TOPIC = "topic-signal"
EXPR = "gpt()"
_WAIT_S = 2.0


class _BlockingExecutor(Executor):
    """Yields one frame, then never finishes — the run can only end by cancellation."""

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:
        yield LogData(severity_number=9, severity_text="INFO", body=f"executing {url4}")
        # Set AFTER the yield so the flag means "the run is inside its execute loop", not merely
        # "the task was created" — signalling too early would test a different code path.
        self.started.set()
        await asyncio.Event().wait()


_LOOP_TURNS = 10
"""Loop iterations to yield so a raised signal is actually DELIVERED.

`add_signal_handler` runs its callback on a later loop iteration (the C handler only writes the
self-pipe), so a test that raises a signal and then proceeds without yielding never lets the
handler fire at all — it would pass whatever the code under test does.
"""


class _SelfSignallingStream(InMemoryEventStream):
    """Raises a SECOND SIGTERM from inside the terminal publish, then yields the loop.

    WHY the signal is raised HERE and not from the test body: the invariant is about a signal
    arriving *while the terminal publish is suspended*. Doing it from the test would race the
    latch release, and the await points that a delivered cancellation lands on are these ones —
    so this reproduces the real window instead of approximating it.
    """

    async def publish(self, topic: str, event: OutboundFrame) -> None:
        if isinstance(event, TerminatedEvent):
            os.kill(os.getpid(), signal.SIGTERM)
            for _ in range(_LOOP_TURNS):
                await asyncio.sleep(0)
        await super().publish(topic, event)


async def _terminal_status(stream: InMemoryEventStream) -> str:
    """The run's terminal status, read off the stream.

    Scans rather than taking a fixed frame count: how much telemetry a run emits before it ends
    is an executor detail, and pinning it here would make these tests fail for reasons that have
    nothing to do with cancellation.
    """

    async def _scan() -> str:
        async for event in stream.subscribe(TOPIC, None):
            if isinstance(event, TerminatedEvent):
                return event.data.status
        raise AssertionError("the stream ended with no terminal frame")

    return await asyncio.wait_for(_scan(), timeout=_WAIT_S)


async def _started_run(
    stream: InMemoryEventStream, executor: _BlockingExecutor
) -> asyncio.Task[None]:
    """Drive one run under `cancel_on_signal` and wait until it is genuinely in flight."""
    task = asyncio.create_task(cancel_on_signal(run(stream, executor, TOPIC, EXPR)))
    await asyncio.wait_for(executor.started.wait(), timeout=_WAIT_S)
    return task


@pytest.mark.asyncio
async def test_sigterm_ends_the_run_with_a_stopped_terminal_frame() -> None:
    """The headline: the Job's pod is SIGTERM'd and the topic still gets its terminal frame."""
    stream = InMemoryEventStream()
    executor = _BlockingExecutor()
    task = await _started_run(stream, executor)

    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(task, timeout=_WAIT_S)

    assert await _terminal_status(stream) == "stopped"


@pytest.mark.asyncio
async def test_sigint_is_left_to_asyncio_run() -> None:
    """INVARIANT: SIGINT is NOT ours to take.

    `asyncio.run` installs `Runner._on_sigint`, whose first action is to cancel the main task —
    the same cancellation this helper delivers for SIGTERM, so Ctrl-C already ends the run with
    a terminal frame. Claiming SIGINT here would REPLACE that handler and take over its
    interrupt counting, silently breaking the escalation where a second Ctrl-C force-quits a run
    that will not stop. Pinned because the loss would only ever show up under someone's fingers.
    """
    stream = InMemoryEventStream()
    executor = _BlockingExecutor()
    installed = signal.getsignal(signal.SIGINT)

    task = await _started_run(stream, executor)
    try:
        assert signal.getsignal(signal.SIGINT) is installed
    finally:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(task, timeout=_WAIT_S)


@pytest.mark.asyncio
async def test_a_second_signal_does_not_abort_the_terminal_publish() -> None:
    """INVARIANT: cancellation fires ONCE.

    `lifecycle.run` publishes the terminal frame from inside its `except CancelledError` arm,
    and that publish is an await. A second `task.cancel()` landing there raises straight through
    `contextlib.suppress(Exception)` — CancelledError is a BaseException — destroying the very
    frame the first signal existed to produce. Escalation belongs to the substrate's SIGKILL,
    not to a second handler firing.

    The stream raises the second signal itself, mid-publish — see `_SelfSignallingStream`.
    """
    stream = _SelfSignallingStream()
    executor = _BlockingExecutor()
    task = await _started_run(stream, executor)

    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(task, timeout=_WAIT_S)

    assert await _terminal_status(stream) == "stopped"


@pytest.mark.asyncio
async def test_a_run_that_finishes_on_its_own_is_untouched() -> None:
    """The regression guard: installing handlers must not change the ordinary success path."""
    stream = InMemoryEventStream()

    await asyncio.wait_for(
        cancel_on_signal(run(stream, MockExecutor(), TOPIC, EXPR)), timeout=_WAIT_S
    )

    assert await _terminal_status(stream) == "succeeded"


@pytest.mark.asyncio
async def test_the_handlers_are_removed_when_the_run_ends() -> None:
    """A handler outliving its run would cancel whatever ran next on this loop."""
    before = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

    await asyncio.wait_for(
        cancel_on_signal(run(InMemoryEventStream(), MockExecutor(), TOPIC, EXPR)), timeout=_WAIT_S
    )

    assert {sig: signal.getsignal(sig) for sig in before} == before


@pytest.mark.asyncio
async def test_a_cancellation_we_did_not_cause_still_propagates() -> None:
    """Only OUR cancellation is absorbed.

    Swallowing any CancelledError would make this helper a black hole for an enclosing
    TaskGroup's shutdown — the caller asked for cancellation and must observe it.
    """
    stream = InMemoryEventStream()
    executor = _BlockingExecutor()
    task = await _started_run(stream, executor)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The frame is still published: `lifecycle.run` terminates on its way out either way.
    assert await _terminal_status(stream) == "stopped"
