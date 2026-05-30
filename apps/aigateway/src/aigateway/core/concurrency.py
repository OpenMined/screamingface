"""Per-provider concurrency guardrail for upstream dispatches.

Bounds how many concurrent calls hit a given upstream provider at once via
an :class:`asyncio.Semaphore` registry kept on ``app.state``. Wraps the
retry loop in :mod:`aigateway.routes.chat` so a quota reset isn't
immediately re-exhausted by a thundering herd of concurrent siblings (the
url4 collection-fan-out failure mode that pure reactive retry could not
absorb).

``limit <= 0`` disables the cap (an async-no-op context).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


def _registry(app: Any) -> dict[str, asyncio.Semaphore]:
    reg = getattr(app.state, "provider_semaphores", None)
    if reg is None:
        reg = {}
        app.state.provider_semaphores = reg
    return reg


def _get_or_create_semaphore(app: Any, provider: str, limit: int) -> asyncio.Semaphore:
    reg = _registry(app)
    sem = reg.get(provider)
    # ``_sf_limit`` records the size the semaphore was created with so a
    # config change (e.g. raising AIGW_PROVIDER_MAX_CONCURRENCY) rebuilds it
    # rather than silently keeping the old cap.
    if sem is None or getattr(sem, "_sf_limit", None) != limit:
        sem = asyncio.Semaphore(limit)
        sem._sf_limit = limit  # type: ignore[attr-defined]
        reg[provider] = sem
    return sem


@asynccontextmanager
async def provider_slot(app: Any, provider: str, limit: int) -> AsyncIterator[None]:
    """Acquire a concurrency slot for ``provider`` for the duration of the block.

    With ``limit <= 0`` the guardrail is disabled and entry is immediate.
    Otherwise an ``asyncio.Semaphore(limit)`` keyed by provider gates entry;
    the slot is held across the entire ``with`` body, so wrapping retry means
    a provider's concurrent-pressure ceiling includes retry attempts.
    """
    if limit <= 0:
        yield
        return
    async with _get_or_create_semaphore(app, provider, limit):
        yield
