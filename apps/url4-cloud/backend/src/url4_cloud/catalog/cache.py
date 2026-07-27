"""The identity-keyed model-catalog cache (spec §6.3, §7).

FEATURE: model-catalog discovery. This is the piece that turns "one upstream call per request"
into "one upstream call per credential per TTL", and the piece that keeps an endpoint whose cache
keys come from unverified credentials from becoming a lever against aigateway.

Five behaviours compose here, each closing a specific failure:

- **TTL** — bounds staleness.
- **Per-key single-flight** — a cold start under load must not stampede upstream.
- **Stale-on-error** — an upstream blip must not empty every client's model list.
- **Per-key failure backoff** — single-flight bounds *concurrent* misses; this bounds
  *sequential* ones.
- **Bounded LRU + an upstream semaphore** — distinct keys bypass single-flight entirely, so these
  are what bound memory and upstream load under a flood of distinct credentials.

AIDEV-NOTE: the stale-on-error discipline here deliberately mirrors
``aigateway.core.auth.cf_access.jwks.CloudflareAccessJwks._refresh`` — serve what is cached, refuse
when cold, never fail open. If you change one, look at the other.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from url4_cloud.catalog.port import CatalogError, CatalogSource, Credential, ModelCatalog

logger = logging.getLogger(__name__)


@runtime_checkable
class CatalogService(Protocol):
    """What the REST route needs: a catalog, plus how long it may be cached downstream.

    WHY this is wider than :class:`~url4_cloud.catalog.port.CatalogSource`: ``max_age_s`` is a
    property of *this cache's* entry, not of a catalog, so it has no meaning on a bare adapter.
    The route types against this so a test can inject a fake without subclassing the cache.
    """

    async def fetch(self, credential: Credential) -> ModelCatalog: ...

    def max_age_s(self, credential: Credential) -> int: ...


@dataclass(slots=True)
class _Entry:
    """A cached catalog plus the failure state observed while trying to refresh it.

    INVARIANT: an ``_Entry`` only ever exists for a key that has SUCCEEDED at least once. Failure
    state is therefore a field here rather than a map of its own, which is what makes "a cold
    failure caches nothing" (spec §7) true by construction instead of by convention: a flood of
    bogus credentials gets 401 upstream and leaves no state behind at all.
    """

    catalog: ModelCatalog
    fetched_at: float
    last_error: CatalogError | None = None
    last_error_at: float | None = None


@dataclass(slots=True)
class CacheCounters:
    """Plain counters, lifted into OpenMetrics by the app's metrics wiring.

    WHY not ``prometheus_client`` here: it would put a metrics dependency in the middle of the
    caching logic and make every cache test construct a registry.
    """

    hits: int = 0
    misses: int = 0
    stale_serves: int = 0
    errors: int = 0
    bulkhead_waits: int = 0


class CachedCatalog:
    """A ``CatalogSource`` decorator that caches per credential.

    Being a source itself is what lets the route depend on one type whether or not caching is in
    play, and lets every test here drive a counting in-memory fake instead of HTTP.
    """

    def __init__(
        self,
        source: CatalogSource,
        *,
        ttl_s: float = 300.0,
        stale_max_s: float = 3600.0,
        error_backoff_s: float = 30.0,
        max_entries: int = 256,
        upstream_concurrency: int = 8,
        clock: Callable[[], float] = time.monotonic,
        source_aclose: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._source = source
        # WHY teardown lives here rather than on the source: the app holds the CACHE, so the cache
        # is what its ASGI shutdown hook can reach. Mirrors `Url4Executor(world_aclose=...)`.
        self._source_aclose = source_aclose
        self._ttl_s = ttl_s
        self._stale_max_s = stale_max_s
        self._error_backoff_s = error_backoff_s
        self._max_entries = max_entries
        self._clock = clock
        # WHY monotonic and injected: a wall clock can step backwards (NTP), which would make an
        # entry look arbitrarily fresh or stale; injecting it lets tests age entries without
        # sleeping.
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[ModelCatalog]] = {}
        # WHY built lazily: asyncio.Semaphore binds to the running loop in older idioms, and this
        # object is constructed at import/app-build time, outside any loop.
        self._upstream_concurrency = upstream_concurrency
        self._semaphore: asyncio.Semaphore | None = None
        self.counters = CacheCounters()

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    async def aclose(self) -> None:
        """Release the upstream client, if this service owns one. Idempotent.

        INVARIANT: idempotent because ASGI shutdown may run alongside an explicit close in tests,
        and a second close must not raise.
        """
        aclose, self._source_aclose = self._source_aclose, None
        if aclose is not None:
            await aclose()

    def max_age_s(self, credential: Credential) -> int:
        """Seconds this credential's entry may still be considered fresh, floored at 0.

        Feeds ``Cache-Control: max-age`` so a downstream cache expires in step with this one
        rather than extending staleness past our own TTL.
        """
        entry = self._entries.get(credential.key)
        if entry is None:
            return 0
        remaining = self._ttl_s - (self._clock() - entry.fetched_at)
        return max(0, int(remaining))

    async def fetch(self, credential: Credential) -> ModelCatalog:
        key = credential.key
        now = self._clock()
        fresh = self._fresh(key, now)
        if fresh is not None:
            return fresh
        inflight = self._inflight.get(key)
        if inflight is not None:
            # WHY shield: awaiting a shared Future directly means one waiter's cancellation
            # cancels the Future for EVERY waiter and the leader. Shielding isolates them.
            # AIDEV-NOTE: if the leader itself is cancelled the Future is cancelled in `finally`,
            # so waiters see CancelledError and the client retries — deliberate, since retrying
            # inside the cache risks an unbounded loop.
            return await asyncio.shield(inflight)
        return await self._miss(credential, key, now)

    def _fresh(self, key: str, now: float) -> ModelCatalog | None:
        """The entry for ``key`` if it is still inside the TTL, else ``None``.

        INVARIANT: this is reached BEFORE `fetch` ever awaits — no lock, no task switch — which is
        what makes a warm cache free, and is asserted by
        `test_a_fresh_hit_never_touches_upstream_even_concurrently`.
        """
        entry = self._entries.get(key)
        if entry is None or now - entry.fetched_at > self._ttl_s:
            return None
        self._entries.move_to_end(key)
        self.counters.hits += 1
        return entry.catalog

    async def _miss(self, credential: Credential, key: str, now: float) -> ModelCatalog:
        """No fresh entry and no flight in progress: back off, or lead a refresh."""
        entry = self._entries.get(key)
        if entry is not None and self._inside_backoff(entry, now):
            # WHY serve rather than refetch: a warm caller polling during an aigateway outage
            # would otherwise hit upstream on every single request.
            return self._stale_or_raise(entry, now, entry.last_error)
        self.counters.misses += 1
        return await self._refresh(credential, key)

    async def _refresh(self, credential: Credential, key: str) -> ModelCatalog:
        """Fetch upstream as the single flight for ``key``, settling every waiter identically."""
        future: asyncio.Future[ModelCatalog] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            catalog = await self._fetch_upstream(credential)
        except CatalogError as exc:
            self.counters.errors += 1
            fallback = self._on_failure(key, exc)
            if fallback is not None:
                # INVARIANT: the leader and its waiters agree. Returning stale to the leader while
                # raising at the waiters would make the outcome depend on arrival order.
                future.set_result(fallback)
                return fallback
            future.set_exception(exc)
            # WHY retrieve it here: nothing awaits this Future when there are no waiters, and an
            # unretrieved Future exception makes asyncio log a spurious warning at GC time. Same
            # trick as `Url4Executor.execute`'s early-aclose path.
            future.exception()
            raise
        else:
            self._store(key, catalog)
            future.set_result(catalog)
            return catalog
        finally:
            self._inflight.pop(key, None)
            if not future.done():
                # The leader was cancelled before settling; releasing waiters beats hanging them.
                future.cancel()

    async def _fetch_upstream(self, credential: Credential) -> ModelCatalog:
        """The one place upstream is called, behind the concurrency bulkhead (spec §7)."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._upstream_concurrency)
        if self._semaphore.locked():
            self.counters.bulkhead_waits += 1
        async with self._semaphore:
            return await self._source.fetch(credential)

    def _inside_backoff(self, entry: _Entry, now: float) -> bool:
        if entry.last_error_at is None or entry.last_error is None:
            return False
        return now - entry.last_error_at < self._error_backoff_s

    def _stale_or_raise(
        self, entry: _Entry, now: float, error: CatalogError | None
    ) -> ModelCatalog:
        """Serve the stale entry, or raise once staleness passes the ceiling."""
        if now - entry.fetched_at <= self._stale_max_s:
            self.counters.stale_serves += 1
            logger.warning(
                "serving a stale model catalog (age %.0fs) — upstream refresh is failing",
                now - entry.fetched_at,
            )
            return entry.catalog
        raise error if error is not None else CatalogError("stale catalog exceeded its ceiling")

    def _on_failure(self, key: str, exc: CatalogError) -> ModelCatalog | None:
        """Record the failure against a KNOWN key and decide whether stale service applies.

        INVARIANT: an unknown key records nothing — see :class:`_Entry`. Backoff exists to protect
        established callers during an outage, not to allocate state for arbitrary tokens.
        """
        entry = self._entries.get(key)
        if entry is None:
            return None
        now = self._clock()
        entry.last_error = exc
        entry.last_error_at = now
        if now - entry.fetched_at <= self._stale_max_s:
            self.counters.stale_serves += 1
            logger.warning("model catalog refresh failed; serving cached entry (%s)", exc)
            return entry.catalog
        return None

    def _store(self, key: str, catalog: ModelCatalog) -> None:
        """Insert as most-recently-used and evict down to ``max_entries``."""
        self._entries[key] = _Entry(catalog=catalog, fetched_at=self._clock())
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


__all__ = ["CacheCounters", "CachedCatalog", "CatalogService"]
