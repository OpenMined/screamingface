"""Bounded negative caching for sequential discovery failures."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from aigateway.config import Settings
from aigateway.core.parameter_discovery import DiscoveryError
from aigateway.core.parameter_discovery_cache import CacheLimits, ObservationCache
from aigateway.main import _build_discovery_runtime


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _cache(clock: _Clock, *, failure_ttl: float = 10.0, cap: int = 8) -> ObservationCache:
    return ObservationCache(
        clock=clock,
        limits=CacheLimits(
            ttl_s=1.0,
            stale_ttl_s=2.0,
            max_entries=cap,
            failure_ttl_s=failure_ttl,
        ),
    )


def _sequence(*answers: object):
    calls = {"count": 0}

    async def refresh() -> object:
        answer = answers[min(calls["count"], len(answers) - 1)]
        calls["count"] += 1
        if isinstance(answer, BaseException):
            raise answer
        return answer

    return refresh, calls


@pytest.mark.asyncio
async def test_sequential_cold_failures_are_suppressed_within_failure_ttl() -> None:
    clock = _Clock()
    cache = _cache(clock)
    refresh, calls = _sequence(DiscoveryError("unreachable"))

    first = await cache.get_or_refresh("k", revision="r1", refresh=refresh)
    second = await cache.get_or_refresh("k", revision="r1", refresh=refresh)

    assert first.freshness == second.freshness == "degraded"
    assert first.value is second.value is None
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_failure_ttl_expiry_allows_recovery_refresh() -> None:
    clock = _Clock()
    cache = _cache(clock, failure_ttl=5.0)
    refresh, calls = _sequence(DiscoveryError("unreachable"), "recovered")

    await cache.get_or_refresh("k", revision="r1", refresh=refresh)
    clock.advance(5.1)
    outcome = await cache.get_or_refresh("k", revision="r1", refresh=refresh)

    assert outcome.freshness == "fresh"
    assert outcome.value == "recovered"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_suppressed_failure_does_not_extend_stale_window() -> None:
    clock = _Clock()
    cache = _cache(clock, failure_ttl=5.0)
    await cache.get_or_refresh("k", revision="r1", refresh=_sequence("last-good")[0])
    clock.advance(2.0)
    failure, calls = _sequence(DiscoveryError("unreachable"))

    stale = await cache.get_or_refresh("k", revision="r1", refresh=failure)
    clock.advance(2.0)
    degraded = await cache.get_or_refresh("k", revision="r1", refresh=failure)

    assert stale.freshness == "stale"
    assert stale.value == "last-good"
    assert degraded.freshness == "degraded"
    assert degraded.value is None
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_failure_for_an_old_revision_does_not_suppress_a_new_revision() -> None:
    clock = _Clock()
    cache = _cache(clock)
    refresh, calls = _sequence(DiscoveryError("unreachable"), "new-revision")

    await cache.get_or_refresh("k", revision="r1", refresh=refresh)
    outcome = await cache.get_or_refresh("k", revision="r2", refresh=refresh)

    assert outcome.freshness == "fresh"
    assert outcome.value == "new-revision"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_inflight_failure_for_an_old_revision_does_not_suppress_a_waiter() -> None:
    clock = _Clock()
    cache = _cache(clock)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fail_old_revision() -> object:
        started.set()
        await release.wait()
        raise DiscoveryError("unreachable")

    recovered, calls = _sequence("new-revision")
    old = asyncio.create_task(
        cache.get_or_refresh("shared-key", revision="r1", refresh=fail_old_revision)
    )
    await started.wait()
    new = asyncio.create_task(cache.get_or_refresh("shared-key", revision="r2", refresh=recovered))
    await asyncio.sleep(0)
    release.set()
    old_outcome, new_outcome = await asyncio.gather(old, new)

    assert old_outcome.freshness == "degraded"
    assert new_outcome.freshness == "fresh"
    assert new_outcome.value == "new-revision"
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_negative_entries_share_the_configured_lru_bound() -> None:
    clock = _Clock()
    cache = _cache(clock, cap=2)
    refresh, calls = _sequence(DiscoveryError("unreachable"))

    for key in ("a", "b", "c", "a"):
        await cache.get_or_refresh(key, revision="r1", refresh=refresh)

    assert calls["count"] == 4


def test_production_runtime_wires_the_configured_failure_ttl() -> None:
    runtime = _build_discovery_runtime(Settings(discovery_cache_failure_ttl_seconds=7.0))

    assert runtime is not None
    assert runtime.cache.limits.failure_ttl_s == 7.0


def test_production_failure_ttl_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        Settings(discovery_cache_failure_ttl_seconds=-0.1)
