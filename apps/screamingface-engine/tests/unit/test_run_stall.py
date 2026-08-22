"""Policy tests for the run-stall watcher (OME-948) — fake clock, fake runner, fake audience.

The spine (`test_run_stall_spine.py`) proves a REAL WebSocket client receives the WARN frame
through the real registry and bridge. This module proves the POLICY: when a run warns — only for
a Job stuck in `scheduled` past the bound, and only once per stall episode — and that a probe
failure or a detached audience never corrupts the watch state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from screamingface_engine.run_stall import STALL_MESSAGE, RunStallWatcher
from url4.streaming.interfaces import JobStatus

#: The notice is generic by contract — no quota names, no namespace or Pod identifiers, no
#: internals a caller cannot act on. These tokens must never appear in the body.
_FORBIDDEN = ("quota", "ns-ceiling", "url4-", "namespace", "pod ")


class _FakeRunner:
    """One scripted `JobStatus` per topic; `status` can be made to raise on demand."""

    def __init__(self, statuses: dict[str, JobStatus] | None = None) -> None:
        self.statuses: dict[str, JobStatus] = statuses or {}
        self.raise_on: set[str] = set()

    async def status(self, topic: str) -> JobStatus:
        if topic in self.raise_on:
            raise RuntimeError(f"probe failed for {topic}")
        return self.statuses.get(topic, "not_found")


class _FakeAudience:
    """The registry-shaped collaborator: a topic snapshot and a notify recorder."""

    def __init__(self) -> None:
        self.live: set[str] = set()
        self.frames: list[tuple[str, Any]] = []

    def topics(self) -> frozenset[str]:
        return frozenset(self.live)

    def notify(self, topic: str, frame: Any) -> None:
        self.frames.append((topic, frame))


class _Clock:
    """A mutable monotonic clock the tests advance explicitly."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def _watcher(
    runner: _FakeRunner,
    audience: _FakeAudience,
    clock: _Clock,
    *,
    warn_after_s: float = 60.0,
) -> RunStallWatcher:
    return RunStallWatcher(
        runner,
        audience,
        warn_after_s=warn_after_s,
        clock=clock,
        frame_clock=lambda: datetime(2026, 8, 22, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_no_warn_before_the_bound_and_exactly_once_after() -> None:
    runner = _FakeRunner({"t": "scheduled"})
    audience = _FakeAudience()
    audience.live.add("t")
    clock = _Clock()
    watcher = _watcher(runner, audience, clock, warn_after_s=60.0)

    # First sweep starts the stall clock; nothing is due yet.
    assert await watcher.sweep() == ()
    clock.advance(59.0)
    assert await watcher.sweep() == ()
    # Elapsed == the bound is the pinned boundary: it warns.
    clock.advance(1.0)
    assert await watcher.sweep() == ("t",)
    assert len(audience.frames) == 1
    assert watcher.warned_total == 1
    # Warned once per episode: a later sweep never repeats it.
    clock.advance(3600.0)
    assert await watcher.sweep() == ()
    assert len(audience.frames) == 1
    assert watcher.warned_total == 1


@pytest.mark.asyncio
async def test_running_and_terminal_never_warn_and_clear_tracking() -> None:
    runner = _FakeRunner({"t": "scheduled"})
    audience = _FakeAudience()
    audience.live.add("t")
    clock = _Clock()
    watcher = _watcher(runner, audience, clock)

    await watcher.sweep()
    assert watcher.stuck_count == 1
    runner.statuses["t"] = "running"
    clock.advance(3600.0)
    assert await watcher.sweep() == ()
    assert watcher.stuck_count == 0
    assert audience.frames == []

    runner.statuses["t"] = "failed"
    await watcher.sweep()
    assert watcher.stuck_count == 0


@pytest.mark.asyncio
async def test_coming_back_to_scheduled_restarts_the_clock() -> None:
    runner = _FakeRunner({"t": "scheduled"})
    audience = _FakeAudience()
    audience.live.add("t")
    clock = _Clock()
    watcher = _watcher(runner, audience, clock, warn_after_s=10.0)

    await watcher.sweep()  # tracked at t=1000
    runner.statuses["t"] = "running"
    clock.advance(1000.0)
    await watcher.sweep()  # cleared
    runner.statuses["t"] = "scheduled"
    # A fresh stall episode must sit a full fresh bound — the old clock does not carry over.
    assert await watcher.sweep() == ()
    clock.advance(9.0)
    assert await watcher.sweep() == ()
    clock.advance(1.0)
    assert await watcher.sweep() == ("t",)


@pytest.mark.asyncio
async def test_a_probe_failure_is_tolerated_and_keeps_tracking() -> None:
    runner = _FakeRunner({"t": "scheduled"})
    audience = _FakeAudience()
    audience.live.add("t")
    clock = _Clock()
    watcher = _watcher(runner, audience, clock, warn_after_s=10.0)

    await watcher.sweep()  # tracked at t=1000
    clock.advance(10.0)
    runner.raise_on.add("t")
    # A failed probe costs a missing or late warning, never a crash and never forgotten state.
    assert await watcher.sweep() == ()
    assert watcher.stuck_count == 1
    runner.raise_on.discard("t")
    assert await watcher.sweep() == ("t",)
    assert watcher.warned_total == 1


@pytest.mark.asyncio
async def test_a_topic_leaving_the_audience_is_pruned_and_reconnect_restarts() -> None:
    runner = _FakeRunner({"t": "scheduled"})
    audience = _FakeAudience()
    audience.live.add("t")
    clock = _Clock()
    watcher = _watcher(runner, audience, clock, warn_after_s=10.0)

    await watcher.sweep()  # tracked at t=1000
    clock.advance(3600.0)
    audience.live.discard("t")  # the last socket detached
    assert await watcher.sweep() == ()
    assert watcher.stuck_count == 0  # pruned: a reconnect must not inherit a stale clock
    audience.live.add("t")
    assert await watcher.sweep() == ()  # fresh first_seen; no instant warn
    clock.advance(10.0)
    assert await watcher.sweep() == ("t",)


@pytest.mark.asyncio
async def test_an_empty_audience_is_a_noop() -> None:
    watcher = _watcher(_FakeRunner(), _FakeAudience(), _Clock())
    assert await watcher.sweep() == ()
    assert watcher.stuck_count == 0
    assert watcher.warned_total == 0


@pytest.mark.asyncio
async def test_the_notice_is_a_warn_log_with_the_generic_body() -> None:
    runner = _FakeRunner({"t": "scheduled"})
    audience = _FakeAudience()
    audience.live.add("t")
    clock = _Clock()
    watcher = _watcher(runner, audience, clock, warn_after_s=0.0)

    await watcher.sweep()
    assert len(audience.frames) == 1
    topic, frame = audience.frames[0]
    assert topic == "t"
    assert frame.type == "ai.url4.log"
    assert frame.data.severity_text == "WARN"
    assert frame.data.body == STALL_MESSAGE
    lowered = frame.data.body.lower()
    for token in _FORBIDDEN:
        assert token not in lowered


def test_the_sweep_cadence_derives_from_the_bound_with_a_floor() -> None:
    assert _watcher(_FakeRunner(), _FakeAudience(), _Clock(), warn_after_s=60.0).tick_s == 7.5
    assert _watcher(_FakeRunner(), _FakeAudience(), _Clock(), warn_after_s=4.0).tick_s == 1.0
