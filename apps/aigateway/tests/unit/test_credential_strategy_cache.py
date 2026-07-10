"""SF-282: shared credential-strategy cache single-flights OAuth refresh.

Concurrent chat requests for the same credential must share ONE strategy
instance so its lock serializes refresh — otherwise a fan-out refreshes the
same rotating token N times and the provider rejects the racers (Anthropic
429 refresh_token_conflict).
"""

from __future__ import annotations

import asyncio

import pytest

from aigateway.core.credential_strategy_cache import CredentialStrategyCache
from aigateway.core.oauth_base import BaseOAuthStrategy

# SF-335 / C12 cross-app contract: this window value is mirrored BY CONTRACT
# (not by shared code) with the legacy SF-server OAuth base (see
# apps/server/src/screamingface/plugins/llm_base/oauth_base.py at tag
# legacy-monorepo-2026-07-08); successor CLI clients must keep matching it.
EXPECTED_REFRESH_WINDOW_SECONDS = 60


def test_refresh_window_matches_cross_app_contract() -> None:
    # The one genuinely-shared-yet-unpinned cross-app invariant (SF-335 / C12):
    # if this drifts from the SF-server base, fan-out refresh decisions disagree
    # across the HTTP boundary (SF-282 class). Mirror any change in BOTH apps.
    assert BaseOAuthStrategy.refresh_window_seconds == EXPECTED_REFRESH_WINDOW_SECONDS


def test_get_or_create_caches_per_key() -> None:
    cache = CredentialStrategyCache()
    builds = 0

    def build() -> object:
        nonlocal builds
        builds += 1
        return object()

    a = cache.get_or_create(
        provider="anthropic", auth_type="oauth", credential_name="x", build=build
    )
    b = cache.get_or_create(
        provider="anthropic", auth_type="oauth", credential_name="x", build=build
    )
    assert a is b
    assert builds == 1


def test_distinct_keys_get_distinct_instances() -> None:
    cache = CredentialStrategyCache()
    a = cache.get_or_create(
        provider="anthropic", auth_type="oauth", credential_name="x", build=object
    )
    b = cache.get_or_create(provider="gemini", auth_type="oauth", credential_name="x", build=object)
    c = cache.get_or_create(
        provider="anthropic", auth_type="api_key", credential_name="x", build=object
    )
    d = cache.get_or_create(
        provider="anthropic", auth_type="oauth", credential_name="y", build=object
    )
    assert len({id(a), id(b), id(c), id(d)}) == 4


def test_evict_drops_all_variants_for_a_credential_name() -> None:
    cache = CredentialStrategyCache()
    cache.get_or_create(provider="anthropic", auth_type="oauth", credential_name="x", build=object)
    cache.get_or_create(
        provider="anthropic", auth_type="api_key", credential_name="x", build=object
    )
    kept = cache.get_or_create(
        provider="anthropic", auth_type="oauth", credential_name="y", build=object
    )

    assert cache.evict("x") == 2
    # "y" is untouched — same instance still returned (build not re-invoked).
    again = cache.get_or_create(
        provider="anthropic", auth_type="oauth", credential_name="y", build=lambda: object()
    )
    assert again is kept


def test_none_build_result_is_not_cached() -> None:
    cache = CredentialStrategyCache()
    builds = 0

    def build() -> None:
        nonlocal builds
        builds += 1
        return None

    assert (
        cache.get_or_create(provider="p", auth_type="oauth", credential_name="x", build=build)
        is None
    )
    cache.get_or_create(provider="p", auth_type="oauth", credential_name="x", build=build)
    assert builds == 2  # not cached → rebuilt


class _FakeOAuthStrategy:
    """Minimal stand-in mirroring BaseOAuthStrategy's locked, once-only refresh."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self.refreshes = 0
        self._active = 0
        self.max_concurrent_refresh = 0

    async def get_authorization_header(self) -> dict[str, str]:
        async with self._lock:
            if self._token is None:
                self._active += 1
                self.max_concurrent_refresh = max(self.max_concurrent_refresh, self._active)
                await asyncio.sleep(0.01)  # widen the refresh window
                self.refreshes += 1
                self._token = "tok"
                self._active -= 1
        return {"Authorization": f"Bearer {self._token}"}


@pytest.mark.asyncio
async def test_shared_instance_single_flights_refresh() -> None:
    cache = CredentialStrategyCache()

    async def one_request() -> _FakeOAuthStrategy:
        strategy = cache.get_or_create(
            provider="anthropic",
            auth_type="oauth",
            credential_name="acc:default",
            build=_FakeOAuthStrategy,
        )
        await strategy.get_authorization_header()
        return strategy

    results = await asyncio.gather(*[one_request() for _ in range(25)])
    shared = results[0]
    assert all(r is shared for r in results), "all requests must share one cached instance"
    assert shared.refreshes == 1, "exactly one refresh across the fan-out (single-flight)"
    assert shared.max_concurrent_refresh == 1, "no concurrent refreshes"


@pytest.mark.asyncio
async def test_without_cache_each_request_refreshes_independently() -> None:
    # Contrast: a fresh strategy per request (the old behavior) refreshes N times.
    async def one_request() -> int:
        strategy = _FakeOAuthStrategy()  # not shared
        await strategy.get_authorization_header()
        return strategy.refreshes

    refresh_counts = await asyncio.gather(*[one_request() for _ in range(25)])
    assert sum(refresh_counts) == 25, "without sharing, every request refreshes (the bug)"
