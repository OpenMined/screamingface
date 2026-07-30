"""Phase 5 (OME-479 §5.3): bounded in-memory public-observation cache.

FEATURE: safe dynamic observation cache. Public evidence may be shared across
accounts, keyed by source + canonical model/backend + source revision. These
tests pin: TTL freshness, single-flight refresh, bounded stale-on-error,
revision isolation, LRU bound, and the honesty rule — cold failure yields a
DEGRADED outcome that a provider maps to ``unknown``; it never fabricates fresh
support.
"""

from __future__ import annotations

import asyncio

import pytest

from aigateway.core.parameter_discovery import DiscoveryError
from aigateway.core.parameter_discovery_cache import (
    CacheLimits,
    ObservationCache,
)


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _cache(clock: _FakeClock, *, ttl: float = 60.0, stale: float = 120.0, cap: int = 8):
    return ObservationCache(
        clock=clock, limits=CacheLimits(ttl_s=ttl, stale_ttl_s=stale, max_entries=cap)
    )


def _counting(value: object, *, error: Exception | None = None):
    state = {"n": 0}

    async def refresh():
        state["n"] += 1
        if error is not None:
            raise error
        return value

    return refresh, state


@pytest.mark.asyncio
async def test_cold_miss_refreshes_and_labels_fresh() -> None:
    clock = _FakeClock()
    cache = _cache(clock)
    refresh, state = _counting(["obs"])
    out = await cache.get_or_refresh("or:m:r1", revision="r1", refresh=refresh)
    assert out.freshness == "fresh"
    assert out.value == ["obs"]
    assert state["n"] == 1


@pytest.mark.asyncio
async def test_warm_hit_within_ttl_does_not_refresh() -> None:
    clock = _FakeClock()
    cache = _cache(clock, ttl=60.0)
    refresh, state = _counting(["v1"])
    await cache.get_or_refresh("k", revision="r1", refresh=refresh)
    clock.advance(59.0)
    refresh2, state2 = _counting(["v2"])
    out = await cache.get_or_refresh("k", revision="r1", refresh=refresh2)
    assert out.freshness == "fresh"
    assert out.value == ["v1"]  # served from cache
    assert state2["n"] == 0  # second refresh never ran


@pytest.mark.asyncio
async def test_expired_ttl_triggers_refresh() -> None:
    clock = _FakeClock()
    cache = _cache(clock, ttl=60.0)
    await cache.get_or_refresh("k", revision="r1", refresh=_counting(["v1"])[0])
    clock.advance(61.0)
    refresh2, state2 = _counting(["v2"])
    out = await cache.get_or_refresh("k", revision="r1", refresh=refresh2)
    assert out.value == ["v2"]
    assert out.freshness == "fresh"
    assert state2["n"] == 1


@pytest.mark.asyncio
async def test_revision_change_invalidates_entry() -> None:
    clock = _FakeClock()
    cache = _cache(clock, ttl=600.0)
    await cache.get_or_refresh("k", revision="r1", refresh=_counting(["v1"])[0])
    refresh2, state2 = _counting(["v2"])
    out = await cache.get_or_refresh("k", revision="r2", refresh=refresh2)
    assert out.value == ["v2"]  # r1 entry not reused for r2
    assert state2["n"] == 1


@pytest.mark.asyncio
async def test_refresh_error_within_stale_window_serves_stale() -> None:
    clock = _FakeClock()
    cache = _cache(clock, ttl=60.0, stale=120.0)
    await cache.get_or_refresh("k", revision="r1", refresh=_counting(["v1"])[0])
    clock.advance(100.0)  # past ttl (60), within ttl+stale (180)
    refresh_err, state = _counting(None, error=DiscoveryError("unreachable"))
    out = await cache.get_or_refresh("k", revision="r1", refresh=refresh_err)
    assert out.freshness == "stale"
    assert out.value == ["v1"]
    assert state["n"] == 1  # a refresh was attempted


@pytest.mark.asyncio
async def test_refresh_error_beyond_stale_window_is_degraded() -> None:
    clock = _FakeClock()
    cache = _cache(clock, ttl=60.0, stale=120.0)
    await cache.get_or_refresh("k", revision="r1", refresh=_counting(["v1"])[0])
    clock.advance(200.0)  # past ttl+stale (180)
    out = await cache.get_or_refresh(
        "k", revision="r1", refresh=_counting(None, error=DiscoveryError("unreachable"))[0]
    )
    assert out.freshness == "degraded"
    assert out.value is None


@pytest.mark.asyncio
async def test_cold_failure_is_degraded_not_fabricated() -> None:
    clock = _FakeClock()
    cache = _cache(clock)
    out = await cache.get_or_refresh(
        "k", revision="r1", refresh=_counting(None, error=DiscoveryError("unreachable"))[0]
    )
    assert out.freshness == "degraded"
    assert out.value is None


@pytest.mark.asyncio
async def test_stale_from_other_revision_is_not_served_on_error() -> None:
    clock = _FakeClock()
    cache = _cache(clock, ttl=60.0, stale=600.0)
    await cache.get_or_refresh("k", revision="r1", refresh=_counting(["old"])[0])
    clock.advance(100.0)
    # source revision bumped; the r1 value must NOT be served for r2 even as stale.
    out = await cache.get_or_refresh(
        "k", revision="r2", refresh=_counting(None, error=DiscoveryError("unreachable"))[0]
    )
    assert out.freshness == "degraded"
    assert out.value is None


@pytest.mark.asyncio
async def test_single_flight_refresh_runs_once() -> None:
    clock = _FakeClock()
    cache = _cache(clock)
    state = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_refresh():
        state["n"] += 1
        started.set()
        await release.wait()
        return ["v"]

    t1 = asyncio.create_task(cache.get_or_refresh("k", revision="r1", refresh=slow_refresh))
    await started.wait()  # caller 1 is inside refresh, holding the key lock
    t2 = asyncio.create_task(cache.get_or_refresh("k", revision="r1", refresh=slow_refresh))
    await asyncio.sleep(0)  # let caller 2 reach and block on the lock
    release.set()
    out1, out2 = await asyncio.gather(t1, t2)
    assert state["n"] == 1  # caller 2 waited and reused the fresh entry
    assert out1.value == out2.value == ["v"]


@pytest.mark.asyncio
async def test_lru_bound_evicts_oldest() -> None:
    clock = _FakeClock()
    cache = _cache(clock, ttl=600.0, cap=2)
    await cache.get_or_refresh("a", revision="r", refresh=_counting(["a"])[0])
    await cache.get_or_refresh("b", revision="r", refresh=_counting(["b"])[0])
    await cache.get_or_refresh("c", revision="r", refresh=_counting(["c"])[0])  # evicts "a"
    refresh_a, state_a = _counting(["a2"])
    out = await cache.get_or_refresh("a", revision="r", refresh=refresh_a)
    assert state_a["n"] == 1  # "a" was evicted, so it refreshed again
    assert out.value == ["a2"]


# --- OME-603: in-flight coordination state is bounded by CALLERS, not by keys ------------


def _failing(error: Exception | None = None):
    return _counting(None, error=error or DiscoveryError("unreachable"))


@pytest.mark.asyncio
async def test_successful_refresh_leaves_no_coordination_state() -> None:
    # INVARIANT: once no caller is inside get_or_refresh, the cache holds no
    # per-key coordination state at all — the entry table is the only residue.
    clock = _FakeClock()
    cache = _cache(clock)
    await cache.get_or_refresh("k", revision="r1", refresh=_counting(["v"])[0])
    assert cache.inflight_key_count == 0


@pytest.mark.asyncio
async def test_cold_failures_leave_no_coordination_state() -> None:
    # The entry table is bounded by max_entries; coordination state must be bounded
    # too. Cold failures store nothing, so they are the path that leaks if cleanup
    # is attached to storing rather than to the caller's exit.
    clock = _FakeClock()
    cache = _cache(clock, cap=8)
    for index in range(100):
        out = await cache.get_or_refresh(f"k{index}", revision="r1", refresh=_failing()[0])
        assert out.freshness == "degraded"
    assert cache.inflight_key_count == 0


@pytest.mark.asyncio
async def test_eviction_while_a_refresh_is_in_flight_leaves_no_coordination_state() -> None:
    clock = _FakeClock()
    cache = _cache(clock, ttl=600.0, cap=1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_refresh():
        started.set()
        await release.wait()
        return ["a"]

    task = asyncio.create_task(cache.get_or_refresh("a", revision="r", refresh=slow_refresh))
    await started.wait()  # "a" is mid-refresh and holds its key's lock
    await cache.get_or_refresh("b", revision="r", refresh=_counting(["b"])[0])
    release.set()
    await task
    assert cache.inflight_key_count == 0


@pytest.mark.asyncio
async def test_failed_refresh_coalesces_across_queued_waiters() -> None:
    # WHY: single-flight exists so an outage costs ONE upstream attempt, not one
    # per waiter. Success already coalesces via the entry re-check; failure must too.
    clock = _FakeClock()
    cache = _cache(clock)
    calls = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_failure():
        calls["n"] += 1
        started.set()
        await release.wait()
        raise DiscoveryError("unreachable")

    first = asyncio.create_task(cache.get_or_refresh("k", revision="r", refresh=slow_failure))
    await started.wait()
    second = asyncio.create_task(cache.get_or_refresh("k", revision="r", refresh=slow_failure))
    third = asyncio.create_task(cache.get_or_refresh("k", revision="r", refresh=slow_failure))
    await asyncio.sleep(0)  # let both losers reach and block on the key lock
    release.set()
    outcomes = await asyncio.gather(first, second, third)

    assert calls["n"] == 1  # one upstream attempt for the whole batch
    assert [out.freshness for out in outcomes] == ["degraded"] * 3
    assert all(out.value is None for out in outcomes)
    assert cache.inflight_key_count == 0


@pytest.mark.asyncio
async def test_queued_waiters_reuse_the_stale_label_not_degraded() -> None:
    clock = _FakeClock()
    cache = _cache(clock, ttl=60.0, stale=120.0)
    await cache.get_or_refresh("k", revision="r", refresh=_counting(["good"])[0])
    clock.advance(100.0)  # past ttl, inside the stale window
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_failure():
        started.set()
        await release.wait()
        raise DiscoveryError("unreachable")

    first = asyncio.create_task(cache.get_or_refresh("k", revision="r", refresh=slow_failure))
    await started.wait()
    second = asyncio.create_task(cache.get_or_refresh("k", revision="r", refresh=slow_failure))
    await asyncio.sleep(0)
    release.set()
    out1, out2 = await asyncio.gather(first, second)

    # The loser reuses the winner's OUTCOME, so it keeps the last good value.
    assert out1.freshness == out2.freshness == "stale"
    assert out1.value == out2.value == ["good"]


@pytest.mark.asyncio
async def test_a_caller_arriving_after_a_failed_batch_retries() -> None:
    # INVARIANT: the shared failure is scoped to the in-flight batch, NOT a negative
    # cache. Otherwise continuous traffic could pin the key to degraded forever.
    clock = _FakeClock()
    cache = _cache(clock)
    out = await cache.get_or_refresh("k", revision="r", refresh=_failing()[0])
    assert out.freshness == "degraded"

    recovered, calls = _counting(["back"])
    out2 = await cache.get_or_refresh("k", revision="r", refresh=recovered)
    assert calls["n"] == 1  # the outage record did not suppress the retry
    assert out2.freshness == "fresh"
    assert out2.value == ["back"]
