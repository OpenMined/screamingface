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

from aigateway.core.concurrency import effective_provider_limit, provider_slot


class _Settings:
    """Minimal settings stand-in for the helper."""

    def __init__(self, default: int, overrides: dict[str, int] | None = None) -> None:
        self.provider_max_concurrency = default
        self.provider_max_concurrency_overrides = overrides or {}


def test_effective_limit_returns_global_when_no_override() -> None:
    assert effective_provider_limit(_Settings(4), "claude") == 4


def test_effective_limit_returns_override_when_present() -> None:
    assert effective_provider_limit(_Settings(4, {"gemini": 1}), "gemini") == 1


def test_effective_limit_override_lookup_is_case_insensitive() -> None:
    """Providers in chat.py are lowercase ('gemini'); a Gemini-cased
    override key in the env JSON should still apply."""
    assert effective_provider_limit(_Settings(4, {"Gemini": 1}), "gemini") == 1


def test_effective_limit_other_providers_unaffected_by_override() -> None:
    """A tight gemini override must not throttle claude/codex."""
    s = _Settings(4, {"gemini": 1})
    assert effective_provider_limit(s, "claude") == 4
    assert effective_provider_limit(s, "codex") == 4


def test_effective_limit_family_key_matches_cli_provider() -> None:
    """The gateway derives provider 'gemini-cli' from model 'gemini-cli/...', but
    operators naturally write the family name 'gemini' in the override. The
    family key must match the -cli provider (the SF-233 foot-gun this fixes)."""
    assert effective_provider_limit(_Settings(4, {"gemini": 1}), "gemini-cli") == 1


def test_effective_limit_exact_cli_key_still_matches() -> None:
    assert effective_provider_limit(_Settings(4, {"gemini-cli": 1}), "gemini-cli") == 1


def test_effective_limit_partial_prefix_does_not_match() -> None:
    """Only the full provider or its -cli-stripped family should match; an
    arbitrary prefix must not."""
    assert effective_provider_limit(_Settings(4, {"gem": 1}), "gemini-cli") == 4


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


# STORY: as an operator raising AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES (OME-889),
# I need the gateway log itself to prove which limit is in force — a typo'd env
# var silently falls back to the default and reappears as mystery queueing.
@pytest.mark.asyncio
async def test_semaphore_creation_logs_effective_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app()
    with caplog.at_level("INFO", logger="aigateway.core.concurrency"):
        async with provider_slot(app, "openrouter", 32):
            pass
    messages = [r.getMessage() for r in caplog.records]
    assert any("provider=openrouter" in m and "limit=32" in m for m in messages)


@pytest.mark.asyncio
async def test_reacquisition_at_same_limit_does_not_log_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """INVARIANT: one line per provider per process — the log marks a limit
    taking effect, never per-request traffic."""
    app = _app()
    async with provider_slot(app, "openrouter", 32):
        pass
    # WHY clear: caplog accumulates from test start, so the first (legitimate)
    # creation log would trip the assertion once the app logger runs at INFO.
    caplog.clear()
    with caplog.at_level("INFO", logger="aigateway.core.concurrency"):
        async with provider_slot(app, "openrouter", 32):
            pass
    assert not [r for r in caplog.records if r.name == "aigateway.core.concurrency"]


@pytest.mark.asyncio
async def test_limit_change_logs_new_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """INVARIANT: the latest logged limit is the limit in force — a rebuild
    (config change) must re-announce itself."""
    app = _app()
    async with provider_slot(app, "openrouter", 4):
        pass
    with caplog.at_level("INFO", logger="aigateway.core.concurrency"):
        async with provider_slot(app, "openrouter", 32):
            pass
    messages = [r.getMessage() for r in caplog.records]
    assert any("provider=openrouter" in m and "limit=32" in m for m in messages)


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
