"""Behaviour tests for the identity-keyed catalog cache (OME-625; spec §6.3, §7).

Headless and deterministic: a counting in-memory ``CatalogSource`` plus an injected monotonic
clock, so no test sleeps to age an entry and no test touches the network. Small ``asyncio.sleep``
calls appear only where a test needs two coroutines to genuinely overlap — never to advance the
cache's own notion of time.
"""

from __future__ import annotations

import asyncio

import pytest

from url4_cloud.catalog.cache import CachedCatalog
from url4_cloud.catalog.port import (
    CatalogBadResponse,
    CatalogUnavailable,
    Credential,
    ModelCatalog,
    compute_etag,
)

pytestmark = pytest.mark.asyncio

CRED_A = Credential.derive("token-a")
CRED_B = Credential.derive("token-b")


class FakeClock:
    """A monotonic clock the test advances by hand."""

    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSource:
    """Counts calls, records observed concurrency, and can be made to fail."""

    def __init__(self, *, delay: float = 0.0, fail: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.fail = fail
        self._delay = delay
        self._live = 0
        self.max_concurrent = 0

    async def fetch(self, credential: Credential) -> ModelCatalog:
        self.calls.append(credential.key)
        self._live += 1
        self.max_concurrent = max(self.max_concurrent, self._live)
        try:
            if self._delay:
                await asyncio.sleep(self._delay)
            if self.fail is not None:
                raise self.fail
            # Body is keyed by credential so a cross-caller leak is directly observable.
            body: dict[str, object] = {"object": "list", "data": [{"id": credential.key}]}
            return ModelCatalog(body=body, etag=compute_etag(body))
        finally:
            self._live -= 1


class ExplodingSource:
    """Fails the test if it is ever consulted — proves a path never reaches upstream."""

    async def fetch(self, credential: Credential) -> ModelCatalog:
        raise AssertionError("upstream must not be called on this path")


def build(source: object, clock: FakeClock, **kwargs: object) -> CachedCatalog:
    defaults: dict[str, object] = {
        "ttl_s": 300.0,
        "stale_max_s": 3600.0,
        "error_backoff_s": 30.0,
        "max_entries": 256,
        "upstream_concurrency": 8,
        "clock": clock,
    }
    defaults.update(kwargs)
    return CachedCatalog(source, **defaults)  # type: ignore[arg-type]


# --- TTL ------------------------------------------------------------------


async def test_cold_miss_fetches_once_and_returns_the_catalog() -> None:
    source = FakeSource()
    cache = build(source, FakeClock())
    catalog = await cache.fetch(CRED_A)
    assert catalog.body["data"] == [{"id": CRED_A.key}]
    assert source.calls == [CRED_A.key]


async def test_hit_inside_the_ttl_performs_no_upstream_call() -> None:
    # ACCEPTANCE 3 (spec §11): the whole point of the feature.
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock)
    first = await cache.fetch(CRED_A)
    clock.advance(299.0)
    second = await cache.fetch(CRED_A)
    assert source.calls == [CRED_A.key]
    assert second is first


async def test_entry_older_than_the_ttl_is_refetched() -> None:
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock)
    await cache.fetch(CRED_A)
    clock.advance(301.0)
    await cache.fetch(CRED_A)
    assert source.calls == [CRED_A.key, CRED_A.key]


async def test_a_fresh_hit_never_touches_upstream_even_concurrently() -> None:
    # INVARIANT: the hot path returns before its first await, so it neither locks nor schedules.
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock)
    await cache.fetch(CRED_A)
    cache._source = ExplodingSource()  # type: ignore[attr-defined]
    results = await asyncio.gather(*(cache.fetch(CRED_A) for _ in range(10)))
    assert len({id(item) for item in results}) == 1


# --- identity keying (the byok-correctness property) ----------------------


async def test_two_credentials_never_observe_each_others_catalog() -> None:
    # ACCEPTANCE 4 (spec §11). This is the property that makes the endpoint correct under
    # aigateway `byok`, where the usable model set is per account.
    source = FakeSource()
    cache = build(source, FakeClock())
    first = await cache.fetch(CRED_A)
    second = await cache.fetch(CRED_B)
    assert first.body["data"] == [{"id": CRED_A.key}]
    assert second.body["data"] == [{"id": CRED_B.key}]
    assert sorted(source.calls) == sorted([CRED_A.key, CRED_B.key])


async def test_a_second_credential_does_not_hit_the_first_ones_warm_entry() -> None:
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock)
    await cache.fetch(CRED_A)
    source.calls.clear()
    await cache.fetch(CRED_B)
    assert source.calls == [CRED_B.key]


# --- single-flight --------------------------------------------------------


async def test_twenty_concurrent_misses_on_one_key_cause_exactly_one_fetch() -> None:
    # ACCEPTANCE 5 (spec §11): a cold start under load must not stampede aigateway.
    source = FakeSource(delay=0.02)
    cache = build(source, FakeClock())
    results = await asyncio.gather(*(cache.fetch(CRED_A) for _ in range(20)))
    assert len(source.calls) == 1
    assert all(item.etag == results[0].etag for item in results)


async def test_distinct_keys_are_not_serialised_behind_each_other() -> None:
    # INVARIANT: single-flight is PER KEY. A global lock would make one slow account's refresh
    # block every other account's — the reason this is a dict of futures, not one lock.
    source = FakeSource(delay=0.05)
    cache = build(source, FakeClock())
    creds = [Credential.derive(f"token-{index}") for index in range(5)]
    await asyncio.gather(*(cache.fetch(cred) for cred in creds))
    assert len(source.calls) == 5
    assert source.max_concurrent > 1


# --- stale-on-error -------------------------------------------------------


async def test_a_failed_refresh_serves_the_previous_entry() -> None:
    # INVARIANT: never fail open into "no models" — a catalog blip must not empty every client's
    # model list. Mirrors CloudflareAccessJwks._refresh's stale-on-error discipline.
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock)
    warm = await cache.fetch(CRED_A)
    clock.advance(301.0)
    source.fail = CatalogUnavailable("upstream down")
    served = await cache.fetch(CRED_A)
    assert served.etag == warm.etag


async def test_stale_service_stops_at_stale_max() -> None:
    # INVARIANT: staleness is bounded. Past the ceiling an error beats silently advertising a
    # catalog that may no longer reflect reality.
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock, stale_max_s=600.0)
    await cache.fetch(CRED_A)
    clock.advance(601.0)
    source.fail = CatalogUnavailable("upstream down")
    with pytest.raises(CatalogUnavailable):
        await cache.fetch(CRED_A)


async def test_concurrent_waiters_receive_the_same_stale_value_as_the_leader() -> None:
    # INVARIANT: the leader and its waiters must agree. Serving the leader a stale body while
    # raising at the waiters would make one request's outcome depend on arrival order.
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock)
    warm = await cache.fetch(CRED_A)
    clock.advance(301.0)
    source.fail = CatalogUnavailable("upstream down")
    source._delay = 0.02
    source.calls.clear()  # count only the calls the concurrent burst causes
    results = await asyncio.gather(*(cache.fetch(CRED_A) for _ in range(5)))
    assert all(item.etag == warm.etag for item in results)
    assert len(source.calls) == 1, "the failing refresh must be single-flighted too"


# --- cold failure ---------------------------------------------------------


async def test_a_cold_failure_raises_and_caches_nothing() -> None:
    # ACCEPTANCE 8 + spec §7: this is what closes the cache-key flooding vector. A bogus token
    # gets 401 upstream and must leave NO state behind, or N bogus tokens become N entries.
    source = FakeSource(fail=CatalogBadResponse("garbage"))
    cache = build(source, FakeClock())
    with pytest.raises(CatalogBadResponse):
        await cache.fetch(CRED_A)
    assert cache.entry_count == 0


async def test_concurrent_cold_failures_all_raise_and_cache_nothing() -> None:
    source = FakeSource(delay=0.02, fail=CatalogBadResponse("garbage"))
    cache = build(source, FakeClock())
    results = await asyncio.gather(*(cache.fetch(CRED_A) for _ in range(5)), return_exceptions=True)
    assert all(isinstance(item, CatalogBadResponse) for item in results)
    assert len(source.calls) == 1
    assert cache.entry_count == 0


# --- failure backoff ------------------------------------------------------


async def test_a_failed_refresh_on_a_known_key_backs_off_before_retrying() -> None:
    # WHY: single-flight collapses CONCURRENT misses; this bounds SEQUENTIAL ones, so a warm
    # caller polling during an aigateway outage does not retry upstream on every request.
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock, error_backoff_s=30.0)
    await cache.fetch(CRED_A)
    clock.advance(301.0)
    source.fail = CatalogUnavailable("down")
    await cache.fetch(CRED_A)
    assert len(source.calls) == 2
    clock.advance(10.0)
    await cache.fetch(CRED_A)
    assert len(source.calls) == 2, "inside the backoff window upstream must not be consulted"


async def test_the_backoff_window_expires_and_upstream_is_retried() -> None:
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock, error_backoff_s=30.0)
    await cache.fetch(CRED_A)
    clock.advance(301.0)
    source.fail = CatalogUnavailable("down")
    await cache.fetch(CRED_A)
    clock.advance(31.0)
    await cache.fetch(CRED_A)
    assert len(source.calls) == 3


async def test_recovery_clears_the_failure_state() -> None:
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock)
    await cache.fetch(CRED_A)
    clock.advance(301.0)
    source.fail = CatalogUnavailable("down")
    await cache.fetch(CRED_A)
    clock.advance(31.0)
    source.fail = None
    fresh = await cache.fetch(CRED_A)
    assert fresh.body["data"] == [{"id": CRED_A.key}]
    clock.advance(301.0)
    source.fail = CatalogUnavailable("down again")
    await cache.fetch(CRED_A)
    assert len(source.calls) == 4, "a recovered key must not still be inside the old backoff"


# --- bounded LRU ----------------------------------------------------------


async def test_the_entry_count_is_capped_and_the_oldest_key_is_evicted() -> None:
    # WHY a cap at all: cache keys derive from credentials url4-cloud does not verify, so the
    # honest-caller population is the only thing bounding entries (spec §7).
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock, max_entries=3)
    creds = [Credential.derive(f"token-{index}") for index in range(4)]
    for cred in creds:
        await cache.fetch(cred)
    assert cache.entry_count == 3
    source.calls.clear()
    await cache.fetch(creds[0])
    assert source.calls == [creds[0].key], "the first key should have been evicted"


async def test_reading_a_key_makes_it_recently_used() -> None:
    source = FakeSource()
    clock = FakeClock()
    cache = build(source, clock, max_entries=2)
    first, second, third = (Credential.derive(f"token-{index}") for index in range(3))
    await cache.fetch(first)
    await cache.fetch(second)
    await cache.fetch(first)  # refreshes first's recency
    await cache.fetch(third)  # evicts the least-recently-used, which is now `second`
    source.calls.clear()
    await cache.fetch(first)
    assert source.calls == [], "first was recently used and must have survived eviction"


# --- upstream bulkhead ----------------------------------------------------


async def test_concurrent_upstream_fetches_never_exceed_the_bulkhead() -> None:
    # ACCEPTANCE 6 + spec §7: distinct keys bypass single-flight entirely, so this is the only
    # thing standing between a flood of distinct credentials and aigateway.
    source = FakeSource(delay=0.02)
    cache = build(source, FakeClock(), upstream_concurrency=2)
    creds = [Credential.derive(f"token-{index}") for index in range(10)]
    await asyncio.gather(*(cache.fetch(cred) for cred in creds))
    assert len(source.calls) == 10
    assert source.max_concurrent <= 2
