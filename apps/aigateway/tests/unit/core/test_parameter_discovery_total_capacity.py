"""Positive and negative discovery records share one capacity bound."""

from __future__ import annotations

import asyncio

import pytest

from aigateway.core.parameter_discovery import DiscoveryError
from aigateway.core.parameter_discovery_cache import CacheLimits, ObservationCache


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def advance(self) -> None:
        self.value += 1.0


@pytest.mark.asyncio
async def test_negative_record_evicts_the_oldest_record_from_the_shared_capacity() -> None:
    clock = _Clock()
    cache = ObservationCache(
        clock=clock,
        limits=CacheLimits(
            ttl_s=100.0,
            stale_ttl_s=0.0,
            max_entries=2,
            failure_ttl_s=100.0,
        ),
    )

    async def first_value() -> str:
        return "first"

    async def second_value() -> str:
        return "second"

    async def failure() -> str:
        raise DiscoveryError("unreachable")

    await cache.get_or_refresh("first", revision="r1", refresh=first_value)
    clock.advance()
    await cache.get_or_refresh("second", revision="r1", refresh=second_value)
    clock.advance()
    await cache.get_or_refresh("failure", revision="r1", refresh=failure)

    refresh_calls = 0

    async def refreshed_first() -> str:
        nonlocal refresh_calls
        refresh_calls += 1
        return "refreshed"

    outcome = await cache.get_or_refresh("first", revision="r1", refresh=refreshed_first)

    assert refresh_calls == 1
    assert outcome.value == "refreshed"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_ttl", [0.0, 100.0])
async def test_evicted_stale_entry_cannot_reappear_as_a_ghost_record(
    failure_ttl: float,
) -> None:
    clock = _Clock()
    cache = ObservationCache(
        clock=clock,
        limits=CacheLimits(
            ttl_s=1.0,
            stale_ttl_s=100.0,
            max_entries=2,
            failure_ttl_s=failure_ttl,
        ),
    )

    async def value(name: str) -> str:
        return name

    await cache.get_or_refresh("first", revision="r1", refresh=lambda: value("first"))
    await cache.get_or_refresh("second", revision="r1", refresh=lambda: value("second"))
    clock.value = 2.0

    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    async def delayed_failure() -> str:
        refresh_started.set()
        await release_refresh.wait()
        raise DiscoveryError("unreachable")

    stale_task = asyncio.create_task(
        cache.get_or_refresh("first", revision="r1", refresh=delayed_failure)
    )
    await refresh_started.wait()
    await cache.get_or_refresh("third", revision="r1", refresh=lambda: value("third"))
    release_refresh.set()

    stale = await stale_task
    assert stale.value == "first"
    assert stale.freshness == "stale"

    if failure_ttl == 0:
        # Without a durable failure record, a ghost token only becomes observable
        # when the next real record trims the shared LRU.
        await cache.get_or_refresh("fourth", revision="r1", refresh=lambda: value("fourth"))
    third_refreshes = 0

    async def refresh_third() -> str:
        nonlocal third_refreshes
        third_refreshes += 1
        return "refreshed-third"

    third = await cache.get_or_refresh("third", revision="r1", refresh=refresh_third)

    assert third_refreshes == 0
    assert third.value == "third"


@pytest.mark.asyncio
async def test_queued_loser_reuses_the_winners_stale_outcome_after_eviction() -> None:
    clock = _Clock()
    cache = ObservationCache(
        clock=clock,
        limits=CacheLimits(
            ttl_s=1.0,
            stale_ttl_s=100.0,
            max_entries=1,
            failure_ttl_s=100.0,
        ),
    )

    async def initial() -> str:
        return "last-good"

    await cache.get_or_refresh("shared", revision="r1", refresh=initial)
    clock.value = 2.0
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()
    refresh_calls = 0

    async def delayed_failure() -> str:
        nonlocal refresh_calls
        refresh_calls += 1
        refresh_started.set()
        await release_refresh.wait()
        raise DiscoveryError("unreachable")

    winner = asyncio.create_task(
        cache.get_or_refresh("shared", revision="r1", refresh=delayed_failure)
    )
    await refresh_started.wait()
    loser = asyncio.create_task(
        cache.get_or_refresh("shared", revision="r1", refresh=delayed_failure)
    )

    async def other_value() -> str:
        return "other"

    await cache.get_or_refresh("other", revision="r1", refresh=other_value)
    release_refresh.set()
    outcomes = await asyncio.gather(winner, loser)

    assert refresh_calls == 1
    assert [(outcome.value, outcome.freshness) for outcome in outcomes] == [
        ("last-good", "stale"),
        ("last-good", "stale"),
    ]


@pytest.mark.asyncio
async def test_queued_loser_reuses_fresh_outcome_after_inter_key_eviction() -> None:
    cache = ObservationCache(
        clock=_Clock(),
        limits=CacheLimits(
            ttl_s=100.0,
            stale_ttl_s=0.0,
            max_entries=1,
            failure_ttl_s=0.0,
        ),
    )
    first_refresh_started = asyncio.Event()
    release_first_refresh = asyncio.Event()
    release_other_refresh = asyncio.Event()
    other_refresh_started = asyncio.Event()
    refresh_calls = 0

    async def shared_refresh() -> str:
        nonlocal refresh_calls
        refresh_calls += 1
        if refresh_calls == 1:
            first_refresh_started.set()
            await release_first_refresh.wait()
            # The other-key task enters the ready queue before this key unlocks,
            # so it can evict the winner's entry before the queued loser runs.
            release_other_refresh.set()
        return f"shared-{refresh_calls}"

    async def other_refresh() -> str:
        other_refresh_started.set()
        await release_other_refresh.wait()
        return "other"

    winner = asyncio.create_task(
        cache.get_or_refresh("shared", revision="r1", refresh=shared_refresh)
    )
    await first_refresh_started.wait()
    loser = asyncio.create_task(
        cache.get_or_refresh("shared", revision="r1", refresh=shared_refresh)
    )
    other = asyncio.create_task(cache.get_or_refresh("other", revision="r1", refresh=other_refresh))
    await other_refresh_started.wait()
    release_first_refresh.set()

    outcomes = await asyncio.gather(winner, loser)
    await other

    assert refresh_calls == 1
    assert [(outcome.value, outcome.freshness) for outcome in outcomes] == [
        ("shared-1", "fresh"),
        ("shared-1", "fresh"),
    ]
