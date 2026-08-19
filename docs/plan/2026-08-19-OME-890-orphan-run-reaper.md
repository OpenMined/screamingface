# Orphan Run Reaper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop an Engine run when its last WebSocket subscriber disconnects and does not come back inside a configurable grace window.

**Architecture:** The `ConnectionRegistry` already knows exactly when a topic's audience empties, so it becomes the arm/disarm signal: it calls an `AudienceListener` on the 0→1 and 1→0 transitions. A `RunReaper` policy object holds one `dict[topic, monotonic_deadline]`, and a single background sweep task in `app.py` calls `reaper.sweep()` on a cadence. `sweep()` claims an expired topic by popping it before any `await`, re-verifies that the audience is still gone and the job still exists, then calls the existing idempotent `JobRunner.stop`. The run terminates as a clean `Terminated(stopped)` — no protocol change, no SDK change, no port change.

**Tech Stack:** Python 3.12+, asyncio, FastAPI, pydantic-settings v2, pytest + pytest-asyncio (`asyncio_mode = "strict"`), ruff, pyright, Helm.

**Spec:** `docs/spec/2026-08-19-OME-890-orphan-run-reaper.md`

## Global Constraints

- Stack: `screamingface-engine`, root `apps/screamingface-engine`. All commands run from that directory unless stated.
- Gates (must all be green before every commit): `uv run .claude/scripts/run_gates.py screamingface-engine` from the repo root.
- ruff: `line-length = 100`, `target-version = "py312"`. Lint selects `E, F, I, UP, C901, PLR0911, PLR0912, PLR0915, PLR1702`.
- ruff pylint limits are tight and enforced: **`max-returns = 3`**, `max-branches = 7`, `max-statements = 26`, `max-complexity = 8`. The `_reap` helper in Task 2 is shaped specifically to stay inside `max-returns = 3` — do not refactor it into four `return` statements.
- pytest: `asyncio_mode = "strict"` — every async test needs an explicit `@pytest.mark.asyncio`.
- Coverage gate: `--cov=screamingface_engine --cov=url4.streaming --cov-fail-under=80`.
- **No new dependencies.** `hypothesis` is not in the dev group; the invariant test in Task 2 is a scripted deterministic sequence, not a property-based test.
- Semantic comment anchors are mandatory and the vocabulary is closed: `WHY:`, `INVARIANT:`, `AIDEV-NOTE:`, `FEATURE:`, `STORY:`. Python syntax is `#`. Never add a comment that restates the code.
- Commit messages: conventional, body carries `Refs: OME-890`, **never** a `Co-Authored-By` trailer.
- Tests are append-only. Do not modify or weaken any existing test to make new code pass.
- Files stay under 450 lines.
- `time.monotonic` for all deadlines. Never a wall clock.

## File Structure

| File | Responsibility |
|---|---|
| `src/screamingface_engine/ws/registry.py` (modify) | Gains the `AudienceListener` protocol, a `listen()` composition-root seam, and the two transition calls. Still owns per-topic session state. |
| `src/screamingface_engine/reaper.py` (create) | **Policy only.** Arm/disarm, the deadline map, `sweep()`, and the counters the metrics collector reads. No FastAPI, no task ownership, no imports from `ws`. |
| `src/screamingface_engine/app.py` (modify) | Owns the background sweep task, mirroring the existing `_install_artifact_sweeper`. Wires the reaper to the **real registry**. |
| `src/screamingface_engine/config.py` (modify) | `orphan_grace_s` setting. |
| `src/screamingface_engine/metrics.py` (modify) | `_ReaperCollector` + `register_reaper_metrics`, mirroring `_CatalogCollector`. |
| `src/screamingface_engine/cli.py` (modify) | One comment recording that uvicorn's WS ping defaults are load-bearing. |
| `.claude/scripts/check_layering.py` (modify) | Adds `reaper` to `CONTROL_PLANE`. |
| `deploy/helm/values.yaml`, `deploy/helm/templates/configmap.yaml` (modify) | Expose `config.orphanGraceS`. |

Four test files, one per task: `tests/unit/test_ws_registry_audience.py`, `tests/unit/test_reaper.py`, `tests/unit/test_reaper_wiring.py`, `tests/integration/test_orphan_reaper_spine.py`.

---

## Task 1: Registry audience transitions

The arm/disarm signal. Nothing consumes it yet, which is deliberate — this task is independently reviewable and cannot change any runtime behaviour, because no listener is registered.

**Files:**
- Modify: `apps/screamingface-engine/src/screamingface_engine/ws/registry.py` (add protocol after line 26; modify `__init__` line 51-52, `add` line 54-55, `remove` line 57-63)
- Modify: `apps/screamingface-engine/src/screamingface_engine/ws/__init__.py` (export `AudienceListener`)
- Test: `apps/screamingface-engine/tests/unit/test_ws_registry_audience.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AudienceListener` protocol with `audience_arrived(topic: str) -> None` and `audience_left(topic: str) -> None`, both sync, both returning `None`. `ConnectionRegistry.listen(audience: AudienceListener) -> None`.

- [ ] **Step 1: Write the failing test**

Create `apps/screamingface-engine/tests/unit/test_ws_registry_audience.py`:

```python
"""The registry's audience-transition edges — the arm/disarm signal the reaper listens to.

FEATURE: tie a run's lifetime to its audience (OME-890).
"""

from screamingface_engine.ws.registry import ConnectionRegistry


class _Recorder:
    """Records transitions in order, as ("arrived"|"left", topic) pairs."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def audience_arrived(self, topic: str) -> None:
        self.events.append(("arrived", topic))

    def audience_left(self, topic: str) -> None:
        self.events.append(("left", topic))


def test_first_subscriber_arrives_and_last_one_leaves() -> None:
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add("t")
    registry.remove("t")

    assert recorder.events == [("arrived", "t"), ("left", "t")]


def test_second_watcher_is_not_an_arrival_and_first_leaver_is_not_a_departure() -> None:
    # INVARIANT: two sockets may legitimately observe one run. The reaper must arm only when
    # the LAST of them goes, never when one of two goes.
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add("t")
    registry.add("t")
    registry.remove("t")

    assert recorder.events == [("arrived", "t")]

    registry.remove("t")

    assert recorder.events == [("arrived", "t"), ("left", "t")]


def test_notifier_created_session_still_reads_the_first_add_as_an_arrival() -> None:
    # WHY: `add_notifier` creates a session at ZERO subscribers, so a naive "session already
    # existed" check would swallow the arrival and leave the reaper armed on a watched run.
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add_notifier("t", lambda frame: None)
    registry.add("t")

    assert recorder.events == [("arrived", "t")]


def test_remove_without_add_fires_nothing() -> None:
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.remove("never-attached")

    assert recorder.events == []


def test_repeated_remove_does_not_fire_left_twice() -> None:
    # INVARIANT: `audience_left` is edge-triggered. A double fire would re-arm a topic whose
    # window the reaper may have already closed.
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add("t")
    registry.remove("t")
    registry.remove("t")

    assert recorder.events == [("arrived", "t"), ("left", "t")]


def test_transitions_are_per_topic() -> None:
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add("a")
    registry.add("b")
    registry.remove("a")

    assert recorder.events == [("arrived", "a"), ("arrived", "b"), ("left", "a")]


def test_registry_without_a_listener_behaves_exactly_as_before() -> None:
    # INVARIANT: the listener is optional. Every existing test builds a bare registry.
    registry = ConnectionRegistry()

    registry.add("t")
    registry.remove("t")  # must not raise
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/screamingface-engine && uv run pytest tests/unit/test_ws_registry_audience.py -v`

Expected: FAIL — `AttributeError: 'ConnectionRegistry' object has no attribute 'listen'`.

- [ ] **Step 3: Write the minimal implementation**

In `src/screamingface_engine/ws/registry.py`, add `Protocol` to the `typing` imports (the file currently imports `Callable` from `collections.abc` and `dataclass, field` from `dataclasses`; add `from typing import Protocol`), then insert this after the `Notify` type alias (after line 26) and before `class _Session`:

```python
class AudienceListener(Protocol):
    """Where the registry announces a topic's audience arriving and leaving.

    FEATURE: tie a run's lifetime to its audience (OME-890).

    INVARIANT: both methods are synchronous and must not raise. They run inside `add`/`remove`,
    and `remove` runs in the WS endpoint's `finally` — a path that also executes under
    cancellation, where an exception would mask the very disconnect it is reporting.
    """

    def audience_arrived(self, topic: str) -> None:
        """``topic`` went from no subscribers to one."""

    def audience_left(self, topic: str) -> None:
        """``topic``'s last subscriber disconnected."""
```

Replace `ConnectionRegistry.__init__`, `add`, and `remove` (lines 51-63) with:

```python
    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}
        self._audience: AudienceListener | None = None

    def listen(self, audience: AudienceListener) -> None:
        """Register the one listener for audience transitions — COMPOSITION ROOT ONLY.

        A setter rather than a constructor argument because the registry is built before the
        reaper that watches it, and the reaper needs the registry (`app.py::create_app`).
        """
        self._audience = audience

    def add(self, topic: str) -> None:
        session = self._sessions.setdefault(topic, _Session())
        session.subscribers += 1
        # INVARIANT: 0->1 ONLY. `add_notifier` can create a session at zero subscribers, and the
        # second of two watchers attaching must not read as "the audience arrived".
        if session.subscribers == 1 and self._audience is not None:
            self._audience.audience_arrived(topic)

    def remove(self, topic: str) -> None:
        session = self._sessions.get(topic)
        if session is None:
            return
        session.subscribers -= 1
        if session.subscribers <= 0:
            del self._sessions[topic]
            # INVARIANT: 1->0 ONLY, and announced AFTER the session is discarded, so a listener
            # that asks `has_subscriber` from inside the callback gets the post-transition answer.
            if self._audience is not None:
                self._audience.audience_left(topic)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/screamingface-engine && uv run pytest tests/unit/test_ws_registry_audience.py -v`
Expected: PASS (7 tests)

Then run the whole suite — no existing test may break:
Run: `cd apps/screamingface-engine && uv run pytest -q`
Expected: PASS, same count as before plus 7.

- [ ] **Step 5: Export the protocol**

In `src/screamingface_engine/ws/__init__.py`, add `AudienceListener` to the imports from `.registry` and to `__all__`, keeping the existing alphabetical order of `__all__`.

- [ ] **Step 6: Run the gates**

Run: `cd /home/junior/workspace/screamingface && uv run .claude/scripts/run_gates.py screamingface-engine`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add apps/screamingface-engine/src/screamingface_engine/ws/registry.py \
        apps/screamingface-engine/src/screamingface_engine/ws/__init__.py \
        apps/screamingface-engine/tests/unit/test_ws_registry_audience.py
git commit -m "$(cat <<'EOF'
feat(screamingface-engine): announce WS audience arrive/leave transitions

The registry knew when a topic's last subscriber left and told nobody. It now
calls an optional AudienceListener on the 0->1 and 1->0 edges, which is the
signal the orphan-run reaper arms and disarms on. No listener is registered
yet, so runtime behaviour is unchanged.

Refs: OME-890
EOF
)"
```

---

## Task 2: The RunReaper policy object

**Files:**
- Create: `apps/screamingface-engine/src/screamingface_engine/reaper.py`
- Test: `apps/screamingface-engine/tests/unit/test_reaper.py`

**Interfaces:**
- Consumes: `AudienceListener` shape from Task 1 (structurally — `reaper.py` does **not** import from `ws`, so the two stay decoupled and the layering gate stays quiet).
- Produces: `RunReaper(job_runner: JobRunner, audience: Audience, *, grace_s: float, clock: Callable[[], float] = time.monotonic, tick_s: float | None = None)`. Properties `tick_s: float`, `armed_count: int`, `reaped_total: int`. Methods `audience_left(topic: str) -> None`, `audience_arrived(topic: str) -> None`, `async sweep() -> tuple[str, ...]`. Also the `Audience` protocol with `async has_subscriber(topic: str) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `apps/screamingface-engine/tests/unit/test_reaper.py`:

```python
"""The orphan-run reaper's policy: arm on audience-empty, disarm on return, stop on expiry.

FEATURE: tie a run's lifetime to its audience (OME-890).

Every test drives an injected clock and calls `sweep()` directly. No test sleeps: a reaper
verified by real time would be both slow and flaky.
"""

import pytest

from screamingface_engine.reaper import RunReaper

GRACE = 120.0


class _FakeClock:
    """A monotonic clock the test advances by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeAudience:
    """Subscriber counts per topic, as the real ConnectionRegistry would answer them."""

    def __init__(self, present: set[str] | None = None) -> None:
        self.present = present or set()

    async def has_subscriber(self, topic: str) -> bool:
        return topic in self.present


class _FakeRunner:
    """Records stop calls; `live` is the set of topics `exists` answers True for."""

    def __init__(self, live: set[str] | None = None, fail_on: set[str] | None = None) -> None:
        self.live = live if live is not None else set()
        self.fail_on = fail_on or set()
        self.stopped: list[str] = []

    async def exists(self, topic: str) -> bool:
        return topic in self.live

    async def stop(self, topic: str) -> None:
        if topic in self.fail_on:
            raise RuntimeError("runner unavailable")
        self.stopped.append(topic)
        self.live.discard(topic)


def _reaper(
    clock: _FakeClock,
    audience: _FakeAudience,
    runner: _FakeRunner,
    grace_s: float = GRACE,
) -> RunReaper:
    return RunReaper(runner, audience, grace_s=grace_s, clock=clock, tick_s=10.0)


@pytest.mark.asyncio
async def test_an_armed_run_is_stopped_once_the_window_closes() -> None:
    clock, audience, runner = _FakeClock(), _FakeAudience(), _FakeRunner(live={"t"})
    reaper = _reaper(clock, audience, runner)

    reaper.audience_left("t")
    clock.advance(GRACE)

    assert await reaper.sweep() == ("t",)
    assert runner.stopped == ["t"]
    assert reaper.armed_count == 0
    assert reaper.reaped_total == 1


@pytest.mark.asyncio
async def test_nothing_happens_before_the_window_closes() -> None:
    clock, audience, runner = _FakeClock(), _FakeAudience(), _FakeRunner(live={"t"})
    reaper = _reaper(clock, audience, runner)

    reaper.audience_left("t")
    clock.advance(GRACE - 0.01)

    assert await reaper.sweep() == ()
    assert runner.stopped == []
    assert reaper.armed_count == 1


@pytest.mark.asyncio
async def test_a_subscriber_returning_inside_the_window_saves_the_run() -> None:
    # STORY: as a researcher whose wifi blipped, my reconnected notebook keeps its evaluation.
    clock, audience, runner = _FakeClock(), _FakeAudience(), _FakeRunner(live={"t"})
    reaper = _reaper(clock, audience, runner)

    reaper.audience_left("t")
    clock.advance(GRACE / 2)
    reaper.audience_arrived("t")
    clock.advance(GRACE)

    assert await reaper.sweep() == ()
    assert runner.stopped == []
    assert reaper.armed_count == 0


@pytest.mark.asyncio
async def test_a_subscriber_present_at_expiry_is_re_checked_and_the_run_survives() -> None:
    # INVARIANT: claim-then-verify. Even with a stale arm — a disarm that never arrived — the
    # sweep asks the registry again before stopping anything, because reaping a watched run is
    # far worse than reaping late.
    clock, audience, runner = _FakeClock(), _FakeAudience(), _FakeRunner(live={"t"})
    reaper = _reaper(clock, audience, runner)

    reaper.audience_left("t")
    audience.present.add("t")  # the arm is stale; the registry disagrees
    clock.advance(GRACE)

    assert await reaper.sweep() == ()
    assert runner.stopped == []
    assert reaper.armed_count == 0


@pytest.mark.asyncio
async def test_a_finished_run_is_not_stopped() -> None:
    # INVARIANT: no second terminal frame. `exists` is False once the run is terminal, and on
    # the k8s runner a stop would DELETE the finished Job before its replay-guard TTL.
    clock, audience, runner = _FakeClock(), _FakeAudience(), _FakeRunner(live=set())
    reaper = _reaper(clock, audience, runner)

    reaper.audience_left("t")
    clock.advance(GRACE)

    assert await reaper.sweep() == ()
    assert runner.stopped == []


@pytest.mark.asyncio
async def test_a_topic_that_never_started_a_run_is_dropped_quietly() -> None:
    clock, audience, runner = _FakeClock(), _FakeAudience(), _FakeRunner(live=set())
    reaper = _reaper(clock, audience, runner)

    reaper.audience_left("attached-then-left-without-starting")
    clock.advance(GRACE)

    assert await reaper.sweep() == ()
    assert reaper.armed_count == 0


@pytest.mark.asyncio
async def test_flapping_leaves_exactly_one_arm_and_the_last_one_wins() -> None:
    clock, audience, runner = _FakeClock(), _FakeAudience(), _FakeRunner(live={"t"})
    reaper = _reaper(clock, audience, runner)

    for _ in range(5):
        reaper.audience_left("t")
        clock.advance(1.0)
        reaper.audience_arrived("t")
    reaper.audience_left("t")

    assert reaper.armed_count == 1

    clock.advance(GRACE - 0.01)
    assert await reaper.sweep() == ()  # measured from the LAST leave, not the first

    clock.advance(0.01)
    assert await reaper.sweep() == ("t",)


@pytest.mark.asyncio
async def test_a_second_sweep_does_not_stop_the_run_again() -> None:
    clock, audience, runner = _FakeClock(), _FakeAudience(), _FakeRunner(live={"t"})
    reaper = _reaper(clock, audience, runner)

    reaper.audience_left("t")
    clock.advance(GRACE)
    await reaper.sweep()
    clock.advance(GRACE)

    assert await reaper.sweep() == ()
    assert runner.stopped == ["t"]


@pytest.mark.asyncio
async def test_a_failed_stop_is_retried_rather_than_abandoned() -> None:
    # INVARIANT: giving up would hand the run back to the 16h ceiling — the exact spend this
    # module exists to stop. A transient runner error must re-arm.
    clock, audience = _FakeClock(), _FakeAudience()
    runner = _FakeRunner(live={"t"}, fail_on={"t"})
    reaper = _reaper(clock, audience, runner)

    reaper.audience_left("t")
    clock.advance(GRACE)

    assert await reaper.sweep() == ()
    assert reaper.armed_count == 1  # re-armed, not dropped

    runner.fail_on.clear()
    clock.advance(reaper.tick_s)

    assert await reaper.sweep() == ("t",)
    assert runner.stopped == ["t"]


@pytest.mark.asyncio
async def test_only_the_due_topics_are_swept() -> None:
    clock, audience = _FakeClock(), _FakeAudience()
    runner = _FakeRunner(live={"early", "late"})
    reaper = _reaper(clock, audience, runner)

    reaper.audience_left("early")
    clock.advance(GRACE / 2)
    reaper.audience_left("late")
    clock.advance(GRACE / 2)

    assert await reaper.sweep() == ("early",)
    assert reaper.armed_count == 1


@pytest.mark.asyncio
async def test_armed_implies_no_subscriber_across_a_scripted_sequence() -> None:
    # INVARIANT (the whole safety property, stated once): a topic is armed only while its
    # audience is empty, and the deadline map never grows without bound. Scripted rather than
    # property-based because `hypothesis` is not a dependency of this stack.
    clock, audience = _FakeClock(), _FakeAudience()
    runner = _FakeRunner(live={"a", "b", "c"})
    reaper = _reaper(clock, audience, runner)
    topics = ("a", "b", "c")

    script = [
        ("arrive", "a"), ("arrive", "b"), ("leave", "a"), ("tick", 30.0),
        ("arrive", "a"), ("leave", "b"), ("leave", "c"), ("tick", 200.0),
        ("arrive", "c"), ("leave", "a"), ("tick", 5.0), ("leave", "c"),
        ("tick", 500.0), ("arrive", "b"),
    ]
    for action, value in script:
        if action == "arrive":
            audience.present.add(str(value))
            reaper.audience_arrived(str(value))
        elif action == "leave":
            audience.present.discard(str(value))
            reaper.audience_left(str(value))
        else:
            clock.advance(float(value))
            await reaper.sweep()
        assert reaper.armed_count <= len(topics)
        for topic in topics:
            if reaper.is_armed(topic):
                assert not await audience.has_subscriber(topic), (
                    f"{topic} is armed while its audience is present"
                )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/screamingface-engine && uv run pytest tests/unit/test_reaper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'screamingface_engine.reaper'`.

- [ ] **Step 3: Write the minimal implementation**

Create `apps/screamingface-engine/src/screamingface_engine/reaper.py`:

```python
"""Stops runs whose audience has gone and not come back.

FEATURE: tie a run's lifetime to its audience (OME-890).

STORY: as a researcher whose notebook kernel died mid-evaluation, I do not keep paying for a
run nobody can receive, and the next evaluation gets its concurrency slot back.

WHY this module exists: the 428 gate (`rest/routes.py::_require_subscriber`) proves an audience
exists when a run starts, and then nothing ever asks again. A client that dies before it can
send `ai.url4.stop` — `kill -9`, a Jupyter kernel restart, laptop sleep, a network partition —
leaves the run issuing paid model calls until `job_deadline_s` (16h), holding one of
`local_max_concurrent_runs` slots and the gateway's per-provider slots the whole time. This
closes the loop: the audience leaving arms a grace window, the audience returning disarms it,
and expiry stops the run through the same idempotent `JobRunner.stop` the explicit paths use.

AIDEV-NOTE: POLICY ONLY — no FastAPI, no task ownership, and deliberately no import from `ws`.
The sweep loop lives in `app.py::_install_orphan_reaper`, beside the artifact sweeper it is
modelled on. The registry's `AudienceListener` is satisfied structurally, which is what keeps
these two modules decoupled.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

from url4.streaming.interfaces import JobRunner

_logger = logging.getLogger(__name__)

_MIN_TICK_S = 1.0
_TICKS_PER_GRACE = 8
"""How many sweeps fit inside one grace window. WHY derived rather than a second setting: reap
latency is `grace` to `grace + grace/8`, so an operator tunes ONE knob and gets a bounded
overshoot, instead of two knobs that can be set into disagreement."""


class Audience(Protocol):
    """The subscriber question, as `ConnectionRegistry` answers it."""

    async def has_subscriber(self, topic: str) -> bool: ...


class RunReaper:
    """Arms a grace window when a topic's audience empties; stops the run if it stays empty.

    INVARIANT: `audience` is the REAL `ConnectionRegistry` — never the `SubscriberGate` DI seam.
    `DenyAllGate` and the tests' `FixedGate(False)` answer "nobody is listening" for EVERY
    topic. That is harmless as an admission gate, where the result is a visible refused start,
    and catastrophic here, where it means "stop every run in this process". Same call as
    `rest/routes.py::_deps` taking `registry` over `interest` for session state.

    INVARIANT: deadlines are monotonic. A wall clock would let an NTP step or a suspend jump
    expire a window that has not elapsed, and reap a live run.
    """

    def __init__(
        self,
        job_runner: JobRunner,
        audience: Audience,
        *,
        grace_s: float,
        clock: Callable[[], float] = time.monotonic,
        tick_s: float | None = None,
    ) -> None:
        self._job_runner = job_runner
        self._audience = audience
        self._grace_s = grace_s
        self._clock = clock
        self._tick_s = (
            tick_s if tick_s is not None else max(_MIN_TICK_S, grace_s / _TICKS_PER_GRACE)
        )
        self._deadlines: dict[str, float] = {}
        self._reaped_total = 0

    @property
    def tick_s(self) -> float:
        """Seconds between sweeps. The loop in `app.py` reads its cadence from here."""
        return self._tick_s

    @property
    def armed_count(self) -> int:
        """Topics currently inside a grace window.

        WHY exposed: it is the /metrics gauge, and a value that never returns to zero is how an
        operator sees that sweeps have stopped running.
        """
        return len(self._deadlines)

    @property
    def reaped_total(self) -> int:
        """Runs stopped for having no audience, since boot."""
        return self._reaped_total

    def is_armed(self, topic: str) -> bool:
        """Whether ``topic`` is inside a grace window."""
        return topic in self._deadlines

    # --- AudienceListener (satisfied structurally; see ws.registry.AudienceListener) ---

    def audience_left(self, topic: str) -> None:
        """Arm: ``topic`` has until now + grace to get its audience back."""
        self._deadlines[topic] = self._clock() + self._grace_s

    def audience_arrived(self, topic: str) -> None:
        """Disarm: somebody is listening again."""
        self._deadlines.pop(topic, None)

    async def sweep(self) -> tuple[str, ...]:
        """Stop every armed run whose grace window has closed; return the topics stopped.

        Split from the loop that calls it so tests drive the policy against an injected clock
        with no sleeps at all.
        """
        now = self._clock()
        due = [topic for topic, deadline in self._deadlines.items() if now >= deadline]
        reaped: list[str] = []
        for topic in due:
            if await self._reap(topic, now):
                reaped.append(topic)
        return tuple(reaped)

    async def _reap(self, topic: str, now: float) -> bool:
        """Stop one expired topic's run; ``True`` when it was actually stopped.

        AIDEV-NOTE: this stays within ruff's `max-returns = 3`. The two guards share one
        `or` deliberately — do not split them into separate `return False` branches.
        """
        # INVARIANT: the topic is CLAIMED — popped — before the first `await`. On a
        # single-threaded loop that makes "this window closed and it is mine to decide" one
        # atomic step, so a reconnect cannot land between the check and the claim. One arriving
        # afterwards simply finds nothing armed, which is the same end state as a disarm.
        self._deadlines.pop(topic, None)
        # First guard: the audience came back and the disarm was missed or raced.
        # Second guard: the run is already terminal. `stop` is idempotent, but on the k8s runner
        # it DELETEs the Job, which would drop a finished Job before the TTL that is its
        # single-use replay guard. Short-circuit order matters: an in-process dict lookup before
        # a possible Kubernetes API call.
        if await self._audience.has_subscriber(topic) or not await self._job_runner.exists(topic):
            return False
        try:
            await self._job_runner.stop(topic)
        except Exception:
            # INVARIANT: a failed stop RE-ARMS rather than gives up, without bound. Abandoning
            # the topic would hand the run back to the 16h ceiling, which is the exact spend
            # this module exists to prevent; the per-tick warning is the operator's signal that
            # the runner itself needs attention.
            self._deadlines[topic] = now + self._tick_s
            _logger.warning("orphan stop failed topic=%s; will retry", topic, exc_info=True)
            return False
        self._reaped_total += 1
        _logger.info(
            "orphan run reaped topic=%s reason=no_subscriber grace_s=%.0f",
            topic,
            self._grace_s,
        )
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/screamingface-engine && uv run pytest tests/unit/test_reaper.py -v`
Expected: PASS (11 tests)

Run: `cd apps/screamingface-engine && uv run pytest -q`
Expected: PASS, nothing regressed.

- [ ] **Step 5: Add `reaper` to the layering gate's control plane**

In `.claude/scripts/check_layering.py`, add `"reaper",` to the `CONTROL_PLANE` set, in alphabetical position between `"ops"` and `"rest"`.

**Why this is required, not cosmetic:** the gate treats any module in neither half as a *shared leaf* that both halves may import. A new top-level `reaper.py` would silently become one, and `runner/*` would then be allowed to import the control plane's reaper. Naming it here makes that import a gate failure.

Also update the docstring's control-plane list (line ~14) to include `reaper`, and the comment above `CONTROL_PLANE` if it enumerates members.

- [ ] **Step 6: Run the gates**

Run: `cd /home/junior/workspace/screamingface && uv run .claude/scripts/run_gates.py screamingface-engine`
Expected: all green, including `LAYERING OK`.

- [ ] **Step 7: Commit**

```bash
git add apps/screamingface-engine/src/screamingface_engine/reaper.py \
        apps/screamingface-engine/tests/unit/test_reaper.py \
        .claude/scripts/check_layering.py
git commit -m "$(cat <<'EOF'
feat(screamingface-engine): add the orphan-run reaper policy

RunReaper arms a monotonic grace window when a topic's audience empties and
stops the run through the existing idempotent JobRunner.stop if the window
closes with nobody listening. Claim-then-verify means a reconnect at the
boundary keeps its run, and a finished run is never stopped twice.

Policy only: no task ownership, no FastAPI, and no import from ws. Nothing
constructs it yet. `reaper` joins CONTROL_PLANE in the layering gate so it
cannot be mistaken for a shared leaf the run mode may import.

Refs: OME-890
EOF
)"
```

---

## Task 3: Configuration, wiring, and the metrics surface

This is the task that makes the feature live. It also carries the single most important test in the plan (Step 1's trap test).

**Files:**
- Modify: `apps/screamingface-engine/src/screamingface_engine/config.py` (add the setting beside `artifact_sweep_interval_s`)
- Modify: `apps/screamingface-engine/src/screamingface_engine/app.py` (import `RunReaper`; call `_install_orphan_reaper` inside `create_app` after line 110; add the installer beside `_install_artifact_sweeper`)
- Modify: `apps/screamingface-engine/src/screamingface_engine/metrics.py` (add `_ReaperCollector` + `register_reaper_metrics`)
- Modify: `apps/screamingface-engine/src/screamingface_engine/cli.py` (one comment at the `uvicorn.run` calls)
- Modify: `apps/screamingface-engine/deploy/helm/values.yaml`, `apps/screamingface-engine/deploy/helm/templates/configmap.yaml`
- Test: `apps/screamingface-engine/tests/unit/test_reaper_wiring.py`

**Interfaces:**
- Consumes: `RunReaper` from Task 2; `ConnectionRegistry.listen` from Task 1.
- Produces: `Settings.orphan_grace_s: float`; `app.state.reaper: RunReaper | None`; `app.state.reaper_task: asyncio.Task | None`; `register_reaper_metrics(metrics: Metrics, get_reaper: Callable[[], Any]) -> None`.

- [ ] **Step 1: Write the failing test**

Create `apps/screamingface-engine/tests/unit/test_reaper_wiring.py`:

```python
"""How the reaper is wired into the App: what it asks, when it exists, and how it shuts down.

FEATURE: tie a run's lifetime to its audience (OME-890).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from screamingface_engine.app import create_app
from screamingface_engine.config import Settings
from screamingface_engine.reaper import RunReaper

from ._fakes import FixedGate, RecordingJobRunner


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"jwt_secret": "x" * 32, "orphan_grace_s": 120.0}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_the_reaper_asks_the_real_registry_and_never_the_subscriber_gate() -> None:
    # INVARIANT — THE TRAP THIS TEST EXISTS FOR: `DenyAllGate`, and every test that injects
    # `FixedGate(False)`, answers "no subscriber" for EVERY topic. Wiring the reaper to that
    # seam instead of the real registry would stop every run in the process one grace window
    # after boot. A refused start is visible and annoying; a silently killed 4-hour evaluation
    # is not recoverable. Same call as `rest/routes.py::_deps` taking `registry` over
    # `interest`. If this test ever fails, do NOT relax it.
    app = create_app(_settings(), job_runner=RecordingJobRunner(), interest=FixedGate(False))

    reaper = app.state.reaper

    assert isinstance(reaper, RunReaper)
    app.state.registry.add("watched")
    assert reaper.is_armed("watched") is False


@pytest.mark.asyncio
async def test_a_disconnect_arms_the_reaper_through_the_registry() -> None:
    app = create_app(_settings(), job_runner=RecordingJobRunner())
    reaper = app.state.reaper

    app.state.registry.add("t")
    assert reaper.is_armed("t") is False

    app.state.registry.remove("t")
    assert reaper.is_armed("t") is True


def test_no_reaper_is_built_without_a_job_runner() -> None:
    # WHY: a stream-only App (`URL4_CLOUD_RUNNER=none`) has nothing to stop, and every unit
    # test that injects no runner must not grow a background task.
    app = create_app(_settings(), job_runner=None)

    assert app.state.reaper is None


def test_a_zero_grace_disables_the_reaper() -> None:
    app = create_app(_settings(orphan_grace_s=0.0), job_runner=RecordingJobRunner())

    assert app.state.reaper is None


def test_a_negative_grace_is_refused_at_startup() -> None:
    with pytest.raises(ValueError):
        _settings(orphan_grace_s=-1.0)


def test_the_default_grace_is_two_minutes() -> None:
    # INVARIANT: uvicorn needs up to ws_ping_interval + ws_ping_timeout (~40s) to notice a
    # partitioned peer, so the default must leave room above that.
    assert Settings(jwt_secret="x" * 32).orphan_grace_s == 120.0


def test_the_sweep_task_starts_and_is_cancelled_with_the_app() -> None:
    app = create_app(_settings(), job_runner=RecordingJobRunner())

    with TestClient(app):
        task = app.state.reaper_task
        assert isinstance(task, asyncio.Task)
        assert not task.done()

    assert app.state.reaper_task.done()


def test_a_stream_only_app_starts_no_sweep_task() -> None:
    app = create_app(_settings(), job_runner=None)

    with TestClient(app):
        assert getattr(app.state, "reaper_task", None) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/screamingface-engine && uv run pytest tests/unit/test_reaper_wiring.py -v`
Expected: FAIL — `Settings` has no field `orphan_grace_s` (pydantic raises on the unexpected kwarg), and `app.state.reaper` does not exist.

If `RecordingJobRunner` is not exported from `tests/unit/_fakes.py`, read that file and use whatever job-runner fake it provides (the module is known to contain `FixedGate` and `RecordingJobRunner`); the fake must supply `async exists(topic) -> bool` and `async stop(topic) -> None`. If its `exists` always returns False, construct it so `exists` can report True, or add a small local fake in this test file rather than modifying the shared one.

- [ ] **Step 3a: Add the setting**

In `src/screamingface_engine/config.py`, add `Field` to the pydantic import (`from pydantic import Field, model_validator`), then add this field immediately after `artifact_sweep_interval_s`:

```python
    # FEATURE: tie a run's lifetime to its audience (OME-890).
    #
    # WHY 120s: a run whose last WebSocket subscriber disconnects gets this long to get one
    # back before the Engine stops it. Uvicorn needs up to ws_ping_interval + ws_ping_timeout
    # (~40s on its defaults) to notice a partitioned peer, so anything much below a minute
    # reaps mostly on clean closes while starting to risk live runs on slow reconnects.
    # 0 disables the reaper entirely.
    #
    # INVARIANT: this bounds SPEND, not correctness — the backstop is still job_deadline_s
    # (16h). Raising it costs money per orphan; lowering it risks a live run.
    orphan_grace_s: float = Field(default=120.0, ge=0.0)
```

- [ ] **Step 3b: Wire the reaper**

In `src/screamingface_engine/app.py`, add the import `from screamingface_engine.reaper import RunReaper` (isort places it after `screamingface_engine.ops`), and add `register_reaper_metrics` to the existing `screamingface_engine.metrics` import.

Replace lines 108-110 with:

```python
    registry = ConnectionRegistry()
    app.state.registry = registry
    app.state.interest = interest if interest is not None else registry
    # FEATURE: tie a run's lifetime to its audience (OME-890).
    _install_orphan_reaper(app, registry, job_runner, settings)
```

Add `register_reaper_metrics(app.state.metrics, lambda: app.state.reaper)` immediately after the existing `register_catalog_metrics(...)` call — note this must come *after* `_install_orphan_reaper` sets `app.state.reaper`, or move it below that call.

Add this function immediately after `_install_artifact_sweeper` (after line 162):

```python
def _install_orphan_reaper(
    app: FastAPI,
    registry: ConnectionRegistry,
    job_runner: JobRunner | None,
    settings: Settings,
) -> None:
    """Wire the orphan-run reaper: arm on audience-empty, sweep on a cadence, stop on expiry.

    FEATURE: tie a run's lifetime to its audience (OME-890). Modelled on
    `_install_artifact_sweeper` above: the policy object owns no task, the loop is an asyncio
    task on the App's own event loop, and shutdown cancels it so nothing outlives the App.

    INVARIANT: the reaper is handed `registry` — the REAL one — and never `app.state.interest`.
    The gate seam answers "no subscriber" for every topic under `DenyAllGate`, which as a reap
    input would stop every run in this process one grace window after boot.
    """
    app.state.reaper = None
    app.state.reaper_task = None
    if job_runner is None or settings.orphan_grace_s <= 0:
        # WHY the early return: a stream-only App has nothing to stop, and an operator may turn
        # the reaper off. Either way no background task is created.
        return
    reaper = RunReaper(job_runner, registry, grace_s=settings.orphan_grace_s)
    app.state.reaper = reaper
    registry.listen(reaper)

    async def _sweep_forever() -> None:
        while True:
            await asyncio.sleep(reaper.tick_s)
            # INVARIANT: one failed sweep must not kill the reaper. An unhandled exception here
            # would end the task silently, and every later orphan would run to the 16h ceiling
            # with no signal at all — worse than the bug this feature fixes, because it would
            # look fixed. Log and keep the cadence.
            try:
                await reaper.sweep()
            except Exception:
                _logger.exception("orphan sweep failed; retrying next interval")

    async def _start() -> None:
        # WHY no sweep at startup, unlike the artifact sweeper: nothing can be armed before a
        # WebSocket has attached and then left, so a boot sweep would have nothing to look at.
        app.state.reaper_task = asyncio.get_running_loop().create_task(_sweep_forever())
        # AIDEV-NOTE: the single-replica assumption is logged, not merely documented in the
        # chart. The audience count is in-process, so a second replica would answer "nobody is
        # listening" for runs another replica is streaming and stop healthy runs. Multi-replica
        # needs a shared SubscriberGate (NATS consumer interest) first.
        _logger.info(
            "orphan reaper armed grace_s=%.0f tick_s=%.0f (assumes a single replica)",
            settings.orphan_grace_s,
            reaper.tick_s,
        )

    async def _stop() -> None:
        task = app.state.reaper_task
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app.router.on_startup.append(_start)
    app.router.on_shutdown.append(_stop)
```

- [ ] **Step 3c: Add the metrics collector**

In `src/screamingface_engine/metrics.py`, add after `_CatalogCollector` and before `register_catalog_metrics`:

```python
class _ReaperCollector:
    """A `prometheus_client` custom collector for the orphan reaper's counters."""

    def __init__(self, get_reaper: Callable[[], Any]) -> None:
        self._get_reaper = get_reaper

    def collect(self) -> Iterable[Any]:
        """Called by `prometheus_client` once per `/metrics` scrape."""
        reaper = self._get_reaper()
        if reaper is None:
            return
        yield CounterMetricFamily(
            "screamingface_engine_orphan_runs_reaped",
            "Runs stopped for having no WebSocket subscriber.",
            value=reaper.reaped_total,
        )
        # WHY a gauge and not just the counter: a value that never returns to zero is how an
        # operator sees that sweeps have stopped running — a silently dead reaper otherwise
        # looks identical to "no orphans happened".
        yield GaugeMetricFamily(
            "screamingface_engine_orphan_runs_armed",
            "Runs currently inside their no-subscriber grace window.",
            value=float(reaper.armed_count),
        )


def register_reaper_metrics(metrics: Metrics, get_reaper: Callable[[], Any]) -> None:
    """Register a `_ReaperCollector` for `get_reaper` on `metrics.registry`."""
    metrics.registry.register(_ReaperCollector(get_reaper))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/screamingface-engine && uv run pytest tests/unit/test_reaper_wiring.py -v`
Expected: PASS (8 tests)

Run: `cd apps/screamingface-engine && uv run pytest -q`
Expected: PASS. Watch specifically for tests that assert on `/metrics` output or on `create_app` state — if any break, that is a real finding to report, not a test to edit.

- [ ] **Step 5: Record the load-bearing uvicorn assumption**

In `src/screamingface_engine/cli.py`, add this comment immediately above the `uvicorn.run(` call in `_serve` (and a one-line pointer above the one in `_serve_local`):

```python
    # INVARIANT (OME-890): uvicorn's WS ping defaults are LOAD-BEARING and deliberately not
    # overridden here. `ws_ping_interval=20` / `ws_ping_timeout=20` are what close a
    # partitioned or sleeping peer's socket within ~40s, which is what fires
    # `ConnectionRegistry.remove` and arms the orphan reaper. Disabling or lengthening them
    # would leave a dead client's run detected only by TCP retransmission timeout (~15-30
    # min) and silently reopen most of the spend OME-890 closed.
```

- [ ] **Step 6: Expose the setting in the chart**

In `deploy/helm/values.yaml`, add to the `config:` block, beside `jobDeadlineS`:

```yaml
  # Seconds a run may keep running with no WebSocket subscriber attached before the App stops
  # it (OME-890). 0 disables the reaper. Keep this comfortably above uvicorn's WS ping window
  # (~40s) so a partitioned client is detected before the window closes.
  orphanGraceS: 120
```

In `deploy/helm/templates/configmap.yaml`, add after the `URL4_CLOUD_JOB_DEADLINE_S` line:

```yaml
  # INVARIANT: this bounds SPEND on runs whose client died, not correctness — job_deadline_s
  # remains the backstop. The reaper's audience count is IN-PROCESS, so this chart's
  # `replicaCount: 1` is load-bearing for it: a second replica would answer "nobody is
  # listening" for runs the other replica is streaming.
  URL4_CLOUD_ORPHAN_GRACE_S: {{ .Values.config.orphanGraceS | quote }}
```

- [ ] **Step 7: Run the gates**

Run: `cd /home/junior/workspace/screamingface && uv run .claude/scripts/run_gates.py screamingface-engine`
Expected: all green.

Also render the chart to prove the template is valid:
Run: `cd apps/screamingface-engine && helm template t deploy/helm --set config.natsUrl=nats://n:4222 | grep ORPHAN`
Expected: one line showing `URL4_CLOUD_ORPHAN_GRACE_S: "120"`.

- [ ] **Step 8: Commit**

```bash
git add apps/screamingface-engine/src/screamingface_engine/config.py \
        apps/screamingface-engine/src/screamingface_engine/app.py \
        apps/screamingface-engine/src/screamingface_engine/metrics.py \
        apps/screamingface-engine/src/screamingface_engine/cli.py \
        apps/screamingface-engine/deploy/helm/values.yaml \
        apps/screamingface-engine/deploy/helm/templates/configmap.yaml \
        apps/screamingface-engine/tests/unit/test_reaper_wiring.py
git commit -m "$(cat <<'EOF'
feat(screamingface-engine): stop runs whose audience never comes back

Wires the orphan reaper into create_app: the real ConnectionRegistry arms it,
a background sweep task modelled on the artifact sweeper drives it, and
URL4_CLOUD_ORPHAN_GRACE_S (default 120s, 0 disables) tunes it. A run whose
last WebSocket subscriber disconnects is now stopped within the grace window
instead of spending for up to job_deadline_s (16h).

The reaper reads the registry and never app.state.interest: DenyAllGate
answers "no subscriber" for every topic, which as a reap input would stop
every run in the process. A test pins that.

Refs: OME-890
EOF
)"
```

---

## Task 4: End-to-end proof on the local spine

**Files:**
- Create: `apps/screamingface-engine/tests/integration/test_orphan_reaper_spine.py`
- Read first (exemplar, do not modify): `apps/screamingface-engine/tests/integration/test_local_spine.py`

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: no source changes. If a test here fails, the defect is in Tasks 1–3.

- [ ] **Step 1: Read the exemplar**

Read `tests/integration/test_local_spine.py` in full. It already builds the whole spine: `POST /token`, a `TestClient` WebSocket at `/ws?ticket=...`, an `AttachEvent`, `GET /?q=...` with the `URL4-Capability` header, and frame assertions with a stub executor (`_EchoExecutor`). Reuse its fixtures and helpers rather than rebuilding them — copy its setup shape, and note how it constructs the local app and injects the executor.

- [ ] **Step 2: Write the failing tests**

Create `apps/screamingface-engine/tests/integration/test_orphan_reaper_spine.py`. Mirror the exemplar's app construction, and pass a small `orphan_grace_s` plus an injected clock or a direct `sweep()` call so no test sleeps. The four scenarios, each asserting behaviour and not just "it ran":

```python
"""End-to-end: a dead client's run is stopped, a reconnecting client's run is not.

FEATURE: tie a run's lifetime to its audience (OME-890).

AIDEV-NOTE: these drive `app.state.reaper.sweep()` directly after moving an injected clock,
rather than waiting on the background task. The task's own cadence is covered in
tests/unit/test_reaper_wiring.py; what these prove is the SPINE — that a real WS disconnect
reaches the reaper and that a real run reaches Terminated(stopped).
"""
```

Test 1 — `test_an_abandoned_run_is_stopped_and_stops_spending`:
1. Mint a token, attach a WebSocket, send the attach frame.
2. `GET /?q=...` with `Prefer: respond-async`; assert 202.
3. Assert the executor has begun (at least one call recorded).
4. Close the WebSocket abruptly (exit the `websocket_connect` context).
5. Advance the injected clock past `orphan_grace_s`; `await app.state.reaper.sweep()`.
6. Assert the returned tuple contains the topic, that the run's terminal frame is
   `TerminatedEvent` with `status == "stopped"`, and — the money assertion — that the
   executor's recorded call count did not increase after the stop.

Test 2 — `test_a_reconnecting_client_keeps_its_run`:
1. Same setup through the 202.
2. Close the WebSocket.
3. Advance the clock to half the grace window and sweep; assert nothing was reaped.
4. Reattach with `AttachEvent(from_sequence=1)`; assert the replayed frames arrive.
5. Advance the clock well past the original deadline and sweep; assert nothing was reaped and
   `app.state.job_runner.exists(topic)` is still True.

Test 3 — `test_an_explicit_stop_is_unchanged_and_is_not_stopped_twice`:
1. Same setup. Send an in-band `ai.url4.stop` frame (and, in a second case, `DELETE /`).
2. Assert the terminal frame and status match today's behaviour exactly.
3. Close the WebSocket, advance the clock past the grace window, sweep.
4. Assert the sweep reaped nothing (the `exists()` guard held) and no second terminal frame
   was published.

Test 4 — `test_reaping_releases_the_concurrency_slot`:
1. Build the local app with `local_max_concurrent_runs=1`.
2. Start one run, then abandon its WebSocket.
3. Assert a second `GET /?q=` returns 503 (`the runner is at capacity`).
4. Advance the clock past the grace window and sweep.
5. Assert the second `GET /?q=` now succeeds — this is the capacity symptom from the issue.

- [ ] **Step 3: Run to verify they fail for the right reason**

Run: `cd apps/screamingface-engine && uv run pytest tests/integration/test_orphan_reaper_spine.py -v`

Expected before Tasks 1–3 are complete: failures. Expected *after* them: these should pass. If a test fails here after Tasks 1–3, treat it as a real defect and fix the source — do not weaken the test.

- [ ] **Step 4: Run the full suite and the gates**

Run: `cd apps/screamingface-engine && uv run pytest -q`
Run: `cd /home/junior/workspace/screamingface && uv run .claude/scripts/run_gates.py screamingface-engine`
Expected: all green, coverage at or above 80.

- [ ] **Step 5: Commit**

```bash
git add apps/screamingface-engine/tests/integration/test_orphan_reaper_spine.py
git commit -m "$(cat <<'EOF'
test(screamingface-engine): prove the orphan reaper end-to-end

Covers the four acceptance criteria on the local spine: an abandoned run is
stopped and issues no further model calls, a client reconnecting inside the
window keeps its run, the explicit stop paths are byte-identical to before,
and reaping releases the concurrency slot a wedged eval was waiting on.

Refs: OME-890
EOF
)"
```

---

## Task 5: Close out

- [ ] **Step 1: Fill in the ledger Outcome**

Edit `docs/work/2026-08-19-OME-890-orphan-run-reaper.md`: set `status: done`, fill `finished: 2026-08-19`, and complete the Outcome section with actual files, the commit SHAs and messages, the gate result line, and any deviations from this plan.

- [ ] **Step 2: Open the PR**

```bash
git push -u origin OME-890-orphan-run-reaper
gh pr create --title "feat(screamingface-engine): stop runs whose client died (OME-890)" --body "$(cat <<'EOF'
## Summary

An Engine run's lifetime was tied to nothing. The 428 gate proved an audience existed at
schedule time and nothing asked again, so a client that died before it could send
`ai.url4.stop` left the run spending for up to `job_deadline_s` (16h) and holding a
concurrency slot.

The registry now announces audience arrive/leave transitions. A `RunReaper` arms a monotonic
grace window when a topic's audience empties and stops the run through the existing idempotent
`JobRunner.stop` if the window closes with nobody listening. Total exposure drops from 57600s
to about 160s (uvicorn's ~40s WS ping detection plus the 120s default grace).

## Test plan

- `tests/unit/test_ws_registry_audience.py` — the 0->1 / 1->0 edges, including two watchers.
- `tests/unit/test_reaper.py` — arm, disarm, claim-then-verify, finished runs, flapping,
  failed-stop retry, and the armed-implies-no-subscriber invariant.
- `tests/unit/test_reaper_wiring.py` — including the trap test that pins the reaper to the
  real registry rather than the `SubscriberGate` seam.
- `tests/integration/test_orphan_reaper_spine.py` — the four acceptance criteria end-to-end.
- Gates: `uv run .claude/scripts/run_gates.py screamingface-engine` green.

## Cross-service contract

None changed. No protocol change, no SDK change, no `JobRunner` port change — the reap
reuses `Terminated(stopped)`.

## Notes for the reviewer

- `reaper` is added to `CONTROL_PLANE` in `check_layering.py` on purpose: without it a new
  top-level module is treated as a shared leaf the run mode may import.
- Uvicorn's WS ping defaults are load-bearing and now commented as such in `cli.py`.
- Single-replica is assumed and logged at startup. Multi-replica needs a shared
  `SubscriberGate` first — see the spec's residual-risk section.

Spec: `docs/spec/2026-08-19-OME-890-orphan-run-reaper.md`
Plan: `docs/plan/2026-08-19-OME-890-orphan-run-reaper.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Close the ticket**

After CI is green and the PR is squash-merged, move OME-890 to Done and add a comment naming the commits, the gate result, and the ledger path. Then remove the worktree: `git worktree remove .claude/worktrees/OME-890-orphan-run-reaper`.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §2 uvicorn ping is load-bearing | Task 3 Step 5 (comment), ledger Acceptance |
| §3.1 the R1 trap | Task 3 Step 1 trap test; `RunReaper` docstring invariant |
| §4.1 edge-armed / tick-verified shape | Tasks 1, 2, 3 |
| §4.2 D1 no port change | Verified: only `exists`/`stop` are used |
| §4.2 D2 one loop | Task 3 `_sweep_forever` |
| §4.2 D3 arm unconditionally | Task 2 `audience_left`; Task 2 test `test_a_topic_that_never_started_a_run_is_dropped_quietly` |
| §4.2 D4 claim before verify | Task 2 `_reap`; test `test_a_subscriber_present_at_expiry_...` |
| §4.2 D5 monotonic | Task 2 default `clock=time.monotonic` |
| §4.2 D6 stop only, no purge | Task 2 `_reap` calls only `stop` |
| §4.2 D7 reuse `Terminated(stopped)` | Task 4 Test 1 asserts the status |
| §4.2 D8 unbounded retry | Task 2 test `test_a_failed_stop_is_retried_rather_than_abandoned` |
| §4.2 D9 layering | Task 2 Step 5 |
| §4.3 race table | Task 2 tests (rows 1, 3, 4, 5, 6) + Task 3 (shutdown row) |
| §5 config + observability | Task 3 Steps 3a, 3c, 6 |
| §6.1 single-replica assumption logged | Task 3 `_start` log line |

Gap found and closed: §6.1 originally said only "documented"; Task 3 now emits a startup log line so the assumption is discoverable at runtime.

**Placeholder scan:** no TBD/TODO. Every code step carries real code. Task 4's tests are specified as numbered scenarios with exact assertions rather than full source, because they must be shaped around `test_local_spine.py`'s existing fixtures, which Step 1 requires reading first — the assertions themselves are fully specified.

**Type consistency:** `audience_arrived` / `audience_left` are spelled identically in Task 1 (protocol), Task 2 (`RunReaper` methods), and Task 3 (wiring). `is_armed`, `armed_count`, `reaped_total`, and `tick_s` are defined in Task 2 and used in Tasks 2, 3, and 4. `orphan_grace_s` is spelled consistently across config, app, tests, and the chart's `orphanGraceS`. `app.state.reaper` and `app.state.reaper_task` are both initialised to `None` in every path.
