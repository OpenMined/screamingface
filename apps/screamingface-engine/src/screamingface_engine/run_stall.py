"""Warns a run's attached client when its Job is stuck in ``scheduled`` past a bound.

FEATURE: surface a generic capacity warning when a Runner Job cannot be scheduled (OME-948).

STORY: as a researcher whose evaluation was accepted but whose Runner Pod can never be created
(the namespace is at its ResourceQuota, or any other scheduling refusal), I am told the runner
service is at capacity instead of staring at a silently non-progressing run for up to 16 hours.

WHY this module exists: ``_map_status`` in the k8s adapter already reports the honest state —
``scheduled`` means the Job exists, no Pod is active, and no terminal condition has fired — and
nobody reads it. The run is accepted (HTTP 202), the Runner process never starts, the App's
``EventConsumer`` is read-only, and the WS bridge keeps heartbeating, so the client waits with
no information until ``activeDeadlineSeconds``. A run that was accepted and never executes is
exactly the case ``notices.warn`` exists for (see its module docstring). This module closes that
gap with the notice channel the App already owns.

INVARIANTS:

- The message is GENERIC — "the runner service is at capacity". Detection is symptom-based
  (``scheduled`` persisting), never cause-based (quota names, namespaces, Pod names), so the
  same notice covers quota refusals, node pressure, and any future scheduling failure.
- Advisory-only. A failed probe or a wrong verdict can cost a missing or late WARNING, and
  nothing else: this module never stops, reschedules, or otherwise touches the run.
- k8s-only by WIRING, never by code: the module is substrate-blind (it reads only
  ``JobStatus`` from the port). ``app.py`` installs it only when ``settings.runner == "k8s"``;
  local mode cannot stall silently and never wires it.
- The stall clock is MONOTONIC (NTP-jump-safe, the reaper's invariant); the frame's ``time`` is
  a datetime — two questions, two seams.

AIDEV-NOTE: POLICY ONLY — no FastAPI, no task ownership, and deliberately no import from ``ws``.
The sweep loop lives in ``app.py::_install_run_stall_watch``, beside the orphan reaper it is
modelled on. The audience's ``AudienceListener`` slot stays the reaper's alone: this watcher
POLLS the registry's topic snapshot rather than listening, which is what keeps the two modules
decoupled and the single-listener invariant intact.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from screamingface_engine import notices
from url4.streaming.interfaces import JobStatus
from url4.streaming.protocol import OutboundFrame

_logger = logging.getLogger(__name__)

_MIN_TICK_S = 1.0
_TICKS_PER_BOUND = 8
"""How many sweeps fit inside one stall bound. WHY derived rather than a second setting: warn
latency is `bound` to `bound + bound/8`, so an operator tunes ONE knob and gets a bounded
overshoot — the same shape as the orphan reaper's `_TICKS_PER_GRACE`."""

STALL_MESSAGE = (
    "the runner could not schedule compute for this run (the runner service is at capacity). "
    "The run has not started — stop it and retry later."
)
"""The generic, user-facing notice body. INVARIANT: no internals — see the module docstring."""

Clock = Callable[[], float]
"""Monotonic elapsed-time source for the stall bound (NTP-jump-safe; see the module docstring)."""

FrameClock = Callable[[], datetime]
"""Wall-clock source for the WARN frame's ``time`` — the seam `_converge_cache` feeds too."""


class RunStatus(Protocol):
    """The one runner question the watch needs, and deliberately nothing else.

    ``not_found`` already answers "the Job is gone", so there is no ``exists`` here — a terminal
    or absent Job is none of the watcher's business. The real ``K8sJobRunner.status`` satisfies
    this structurally.
    """

    async def status(self, topic: str) -> JobStatus: ...


class StallAudience(Protocol):
    """The registry-shaped collaborator: the live topic snapshot to watch and the notice sink.

    Both live on the REAL ``ConnectionRegistry`` (never the ``interest`` DI seam — the same
    invariant as the orphan reaper, for the same reason: a gate that answers "nobody is
    listening" for every topic would stop every run in the process).
    """

    def topics(self) -> frozenset[str]: ...

    def notify(self, topic: str, frame: OutboundFrame) -> None: ...


class RunStallWatcher:
    """Warns each live topic whose Job has been stuck in ``scheduled`` past the bound, once.

    INVARIANT: a run that STARTED, SUCCEEDED, FAILED or went ``timed_out`` is dropped from
    tracking the moment any non-``scheduled`` status is observed — a healthy run must never be
    warned, and a stalled one that heals must not carry its old clock into a later stall.

    INVARIANT: a topic that leaves the audience (its last socket detached) is PRUNED — a later
    reconnect starts a fresh stall clock, so an old ``first_seen`` can never fire an instant
    warn against a run that has meanwhile progressed.

    INVARIANT: one WARN per stall EPISODE. The ``warned`` set is cleared when the topic leaves
    ``scheduled`` or the audience — re-warnings happen only for genuinely new stall episodes.
    """

    def __init__(
        self,
        runner: RunStatus,
        audience: StallAudience,
        *,
        warn_after_s: float,
        clock: Clock = time.monotonic,
        frame_clock: FrameClock = datetime.now,
        tick_s: float | None = None,
    ) -> None:
        self._runner = runner
        self._audience = audience
        self._warn_after_s = warn_after_s
        self._clock = clock
        self._frame_clock = frame_clock
        self._tick_s = (
            tick_s if tick_s is not None else max(_MIN_TICK_S, warn_after_s / _TICKS_PER_BOUND)
        )
        #: monotonic time a topic was first observed stuck; the stall clock.
        self._first_seen: dict[str, float] = {}
        #: topics already warned for their CURRENT stall episode.
        self._warned: set[str] = set()
        self._warned_total = 0

    @property
    def tick_s(self) -> float:
        """Seconds between sweeps. The loop in `app.py` reads its cadence from here."""
        return self._tick_s

    @property
    def stuck_count(self) -> int:
        """Topics currently being tracked as stuck (warned or not yet warned).

        WHY exposed: it is the `/metrics` gauge, and a value that never returns to zero is how
        an operator sees that the watch has stopped working — a silently dead sweep otherwise
        looks exactly like "no stalls happened" (same argument as the reaper's ``armed_count``).
        """
        return len(self._first_seen)

    @property
    def warned_total(self) -> int:
        """Runs warned for an unschedulable Job, since boot."""
        return self._warned_total

    async def sweep(self) -> tuple[str, ...]:
        """Warn every live topic whose stall bound has closed; return the topics warned.

        Split from the loop that calls it so tests drive the policy against an injected clock
        with no sleeps at all.

        INVARIANT: a per-topic ``status()`` failure is tolerated — logged, that topic skipped
        for this tick, its tracking KEPT (a transient probe failure must neither warn nor
        forget; the next tick retries). The reaper's philosophy, verbatim: a failed probe
        re-arms rather than gives up.
        """
        live = self._audience.topics()
        now = self._clock()
        warned: list[str] = []
        for topic in live:
            try:
                status = await self._runner.status(topic)
            except Exception:
                # WHY a broad catch: the probe is a network round trip and can raise any
                # transport/API error the substrate's client raises — enumerating them all
                # here would couple the policy to the substrate. The reaper's stop path is
                # the same shape. A failed probe must never kill the sweep loop.
                _logger.warning(
                    "run-stall status probe failed topic=%s; will retry", topic, exc_info=True
                )
                continue
            if status != "scheduled":
                self._first_seen.pop(topic, None)
                self._warned.discard(topic)
                continue
            self._first_seen.setdefault(topic, now)
            if topic not in self._warned and now - self._first_seen[topic] >= self._warn_after_s:
                self._audience.notify(
                    topic,
                    notices.warn(topic, self._frame_clock, STALL_MESSAGE, {}),
                )
                self._warned.add(topic)
                self._warned_total += 1
                warned.append(topic)
        # INVARIANT: prune topics that left the audience (a socket detached). A stale
        # ``first_seen`` would otherwise make a reconnect warn instantly against an old clock.
        for stale in set(self._first_seen) - live:
            self._first_seen.pop(stale, None)
            self._warned.discard(stale)
        return tuple(warned)


__all__ = [
    "STALL_MESSAGE",
    "Clock",
    "FrameClock",
    "RunStatus",
    "RunStallWatcher",
    "StallAudience",
]
