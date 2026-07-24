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
        # One lock per live key enforces single-flight; dropped when the key leaves.
        self._locks: dict[str, asyncio.Lock] = {}

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
        """
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self._entries.get(key)
            if entry is not None and self._is_fresh(entry, revision):
                self._entries.move_to_end(key)
                return CacheOutcome(value=entry.value, freshness="fresh")

            # Not fresh (cold, expired, or revision changed) → attempt one refresh.
            try:
                value = await refresh()
            except DiscoveryError:
                return self._on_refresh_error(entry, revision)

            self._store(key, _Entry(value=value, stored_at=self._clock.now(), revision=revision))
            return CacheOutcome(value=value, freshness="fresh")

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
        self._entries[key] = entry
        self._entries.move_to_end(key)
        while len(self._entries) > self._limits.max_entries:
            evicted, _ = self._entries.popitem(last=False)
            # Drop the evicted key's lock unless a caller is mid-refresh on it.
            evicted_lock = self._locks.get(evicted)
            if evicted_lock is not None and not evicted_lock.locked():
                self._locks.pop(evicted, None)
