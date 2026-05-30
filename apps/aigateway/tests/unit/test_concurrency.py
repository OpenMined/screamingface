"""Tests for the per-provider concurrency guardrail.

The guardrail bounds concurrent upstream dispatches per provider via an
``asyncio.Semaphore`` registry kept on ``app.state``. ``limit <= 0`` disables
the cap (an async-no-op context).

This stops the url4 collection fan-out from self-DoSing a provider — each
provider quota reset isn't immediately re-exhausted by a thundering herd of
concurrent siblings.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from aigateway.core.concurrency import provider_slot


def _app() -> Any:
    return SimpleNamespace(state=SimpleNamespace())


@pytest.mark.asyncio
async def test_limit_zero_does_not_block() -> None:
    """``limit <= 0`` means 'no cap' — entry must not block on any siblings."""
    app = _app()
    entered: list[int] = []

    async def task(i: int) -> None:
        async with provider_slot(app, "gemini", 0):
            entered.append(i)

    await asyncio.gather(*(task(i) for i in range(5)))
    assert sorted(entered) == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_limit_two_caps_concurrency_at_two() -> None:
    """With ``limit=2``, at most two coroutines hold the slot at once.

    Pins the actual purpose of the guardrail. Without the semaphore the
    observed peak would equal the number of tasks.
    """
    app = _app()
    in_flight = 0
    peak = 0
    release = asyncio.Event()

    async def task() -> None:
        nonlocal in_flight, peak
        async with provider_slot(app, "gemini", 2):
            in_flight += 1
            peak = max(peak, in_flight)
            await release.wait()
            in_flight -= 1

    workers = [asyncio.create_task(task()) for _ in range(5)]
    # Let the scheduler hand each worker a chance to start; the cap must hold
    # the third+ workers outside the slot.
    await asyncio.sleep(0.05)
    assert peak == 2
    release.set()
    await asyncio.gather(*workers)


@pytest.mark.asyncio
async def test_semaphore_is_keyed_per_provider() -> None:
    """A claude slot must not be held against a gemini call."""
    app = _app()
    blocker_release = asyncio.Event()

    async def blocker() -> None:
        async with provider_slot(app, "gemini", 1):
            await blocker_release.wait()

    blocker_task = asyncio.create_task(blocker())
    await asyncio.sleep(0.01)  # let blocker enter

    # A different provider must not block on gemini's full slot.
    entered = False

    async def claude_caller() -> None:
        nonlocal entered
        async with provider_slot(app, "claude", 1):
            entered = True

    await asyncio.wait_for(claude_caller(), timeout=0.5)
    assert entered

    blocker_release.set()
    await blocker_task


@pytest.mark.asyncio
async def test_limit_change_replaces_semaphore() -> None:
    """If the configured limit changes (e.g. settings hot-reload) the next
    acquisition uses a freshly-sized semaphore — old slots don't linger."""
    app = _app()

    async with provider_slot(app, "gemini", 1):
        pass
    first = app.state.provider_semaphores["gemini"]

    async with provider_slot(app, "gemini", 3):
        pass
    second = app.state.provider_semaphores["gemini"]

    assert first is not second
