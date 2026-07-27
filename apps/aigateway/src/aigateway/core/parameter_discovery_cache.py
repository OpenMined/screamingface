"""OME-479 §5.3 — bounded in-memory public-observation cache.

FEATURE: safe dynamic observation cache. Public discovery evidence (§5.2) may be
shared across accounts because it depends only on the PUBLIC source, never on a
caller's credentials. This cache is keyed by ``source + canonical model/backend``
and additionally guarded by the source ``revision`` so a projection-schema bump
never serves evidence gathered under the old shape.

INVARIANT (§5.3): this cache never fabricates fresh support. A cold failure or an
expired-past-stale entry yields a DEGRADED outcome (value ``None``) that a provider
maps to ``unknown`` — it is honest absence, not invented capability.

INVARIANT: single-flight per key — concurrent callers for the same key coalesce
onto ONE refresh; the losers reuse the just-stored fresh entry. No durable store,
no scheduler, no new dependency (§5.3, §11): a process-lifetime ``OrderedDict``.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .parameter_discovery import DiscoveryError

# fresh: within TTL for the requested revision.
# stale: TTL expired but within the bounded stale-on-error window, same revision,
#        and only served when a refresh actually FAILED (never pre-emptively).
# degraded: no trustworthy value — the provider must map this to ``unknown``.
Freshness = Literal["fresh", "stale", "degraded"]


class MonotonicClock(Protocol):
    """Injected time seam — a real monotonic clock in prod, a fake in tests.

    # WHY: TTL math must not depend on wall-clock jumps, and tests must drive time
    # deterministically. The cache never calls ``time`` directly.
    """

    def now(self) -> float: ...


class SystemMonotonicClock:
    """The production ``MonotonicClock``: the process's own monotonic timer.

    # WHY monotonic and not wall time: an NTP correction or a DST change must not
    # expire — or resurrect — cached evidence.
    """

    def now(self) -> float:
        return time.monotonic()


@dataclass(frozen=True)
class CacheLimits:
    """Freshness/size bounds for the observation cache (§5.3)."""

    ttl_s: float
    stale_ttl_s: float
    max_entries: int


@dataclass(frozen=True)
class CacheOutcome:
    """The result of a lookup: a value (or ``None``) plus its trust label."""

    value: Any | None
    freshness: Freshness


@dataclass(frozen=True)
class _Entry:
    value: Any
    stored_at: float
    revision: str


@dataclass
class _InFlight:
    """Coordination state for the callers currently inside ``get_or_refresh`` for one key.

    # WHY: this is state about CALLERS, not about entries. Tying its cleanup to the
    # entry table (drop the lock when the key is evicted) leaks on every path that
    # returns without storing — which is every failure path — and bounds the lock
    # table by "distinct keys ever seen" instead of by concurrency. Owning it here,
    # created by the first caller in and dropped by the last caller out, makes the
    # bound structural: coordination state cannot outnumber in-flight callers.
    """

    lock: asyncio.Lock
    waiters: int = 0
    # Completed refresh attempts for this key within THIS batch. A caller reads it
    # before queuing; if it moved while the caller waited, some other caller already
    # paid for an attempt.
    attempts: int = 0
    # The outcome of the most recent FAILED attempt in this batch, reused by
    # single-flight losers. Cleared on success.
    failure: CacheOutcome | None = None


class ObservationCache:
    """A bounded, single-flight, TTL+stale in-memory cache for public evidence.

    # AIDEV-NOTE: intentionally process-local and unshared — discovery evidence is
    # public and cheap to re-fetch, so a durable/distributed store would add risk
    # (stale secrets, migrations) for no benefit (§5.3 forbids it).
    """

    def __init__(self, *, clock: MonotonicClock, limits: CacheLimits) -> None:
        self._clock = clock
        self._limits = limits
        # OrderedDict doubles as the LRU: most-recently-used is moved to the end,
        # eviction pops from the front.
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        # Live only while callers are inside get_or_refresh for the key (see _InFlight).
        self._inflight: dict[str, _InFlight] = {}

    @property
    def limits(self) -> CacheLimits:
        """The bounds this cache enforces.

        # WHY exposed: a consumer that publishes an expiry window must derive it
        # from the SAME TTL the cache expires on. Passing the TTL separately
        # alongside the cache is a two-source-of-truth seam whose drift is
        # invisible — the contract would advertise a window the cache does not
        # honour.
        """
        return self._limits

    @property
    def inflight_key_count(self) -> int:
        """Keys with live coordination state — i.e. callers currently inside the cache.

        # INVARIANT: zero whenever no caller is inside ``get_or_refresh``. Exposed
        # because "the cache's memory is bounded" is an operational property that
        # must be assertable without reaching into internals.
        """
        return len(self._inflight)

    async def get_or_refresh(
        self,
        key: str,
        *,
        revision: str,
        refresh: Callable[[], Awaitable[Any]],
    ) -> CacheOutcome:
        """Return fresh cached evidence, or refresh once, degrading honestly.

        # INVARIANT: a value is returned ONLY when it is trustworthy for THIS
        # ``revision``. A stale entry from a different revision is never served.
        # INVARIANT: one upstream attempt per batch of contemporaneous callers,
        # whether that attempt succeeds or fails.
        """
        state = self._enter(key)
        # Read BEFORE queuing: if this moves while we wait, someone else attempted.
        observed = state.attempts
        try:
            async with state.lock:
                entry = self._entries.get(key)
                if entry is not None and self._is_fresh(entry, revision):
                    self._entries.move_to_end(key)
                    return CacheOutcome(value=entry.value, freshness="fresh")

                # A single-flight LOSER of a failed attempt: reuse that outcome rather
                # than re-dial a source we just watched fail. Recomputing it would give
                # the same answer anyway — the winner stored nothing and the clock is
                # the only other input.
                if state.failure is not None and state.attempts > observed:
                    return state.failure

                # Not fresh (cold, expired, or revision changed) → attempt one refresh.
                try:
                    value = await refresh()
                except DiscoveryError:
                    state.attempts += 1
                    state.failure = self._on_refresh_error(entry, revision)
                    return state.failure

                state.attempts += 1
                state.failure = None
                self._store(
                    key, _Entry(value=value, stored_at=self._clock.now(), revision=revision)
                )
                return CacheOutcome(value=value, freshness="fresh")
        finally:
            self._leave(key)

    def _enter(self, key: str) -> _InFlight:
        # AIDEV-NOTE: _enter/_leave are deliberately SYNCHRONOUS. With no await
        # between the lookup and the counter change, the event loop cannot interleave
        # another caller here, so the refcount needs no lock of its own.
        state = self._inflight.get(key)
        if state is None:
            state = _InFlight(lock=asyncio.Lock())
            self._inflight[key] = state
        state.waiters += 1
        return state

    def _leave(self, key: str) -> None:
        state = self._inflight.get(key)
        if state is None:  # pragma: no cover - _enter always precedes _leave
            return
        state.waiters -= 1
        if state.waiters <= 0:
            # Last caller out drops the batch — including its failure record, so the
            # next arrival gets a real attempt instead of a pinned outage verdict.
            del self._inflight[key]

    def _is_fresh(self, entry: _Entry, revision: str) -> bool:
        if entry.revision != revision:
            return False
        return (self._clock.now() - entry.stored_at) <= self._limits.ttl_s

    def _on_refresh_error(self, entry: _Entry | None, revision: str) -> CacheOutcome:
        # WHY: fail-soft to the LAST GOOD value only within a bounded window and only
        # for the SAME revision; otherwise fail-closed to degraded rather than invent.
        if entry is not None and entry.revision == revision:
            age = self._clock.now() - entry.stored_at
            if age <= self._limits.ttl_s + self._limits.stale_ttl_s:
                return CacheOutcome(value=entry.value, freshness="stale")
        return CacheOutcome(value=None, freshness="degraded")

    def _store(self, key: str, entry: _Entry) -> None:
        # Eviction touches the entry table ONLY: coordination state has its own
        # lifecycle (_enter/_leave), so there is nothing to reconcile here.
        self._entries[key] = entry
        self._entries.move_to_end(key)
        while len(self._entries) > self._limits.max_entries:
            self._entries.popitem(last=False)
