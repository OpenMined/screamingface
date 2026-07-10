"""SF-323: the connection token endpoint single-flights OAuth refresh through the
same app-scoped ``CredentialStrategyCache`` as chat dispatch.

Before SF-323 the token service built a *fresh* ``BaseOAuthStrategy`` per call,
guarded by its own per-``(account, connection)`` lock. That lock serialized
token↔token only; it could not serialize token↔chat, so a ``GET .../token`` and
a ``POST /v1/chat/completions`` for the same connection each held a *different*
lock and both refreshed the same rotating OAuth token (Anthropic then rejects the
racer with ``429 refresh_token_conflict`` — the exact class SF-282 fixed for
chat↔chat).

The fix routes the token service through the shared cache keyed identically to
chat ``(provider, "oauth", credential_key_for(account_id, connection.id))`` so
both paths resolve ONE strategy instance and contend on its single
``asyncio.Lock``. These tests prove the *cache*, not a singleton test double, is
what shares the instance, and that refresh is single-flighted across BOTH paths.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from aigateway.core.credential_strategy_cache import CredentialStrategyCache
from aigateway.core.errors import AuthError, ReauthRequiredError
from aigateway.core.oauth.store import credential_key_for
from aigateway.core.oauth.token_service import (
    OAuthConnectionTokenError,
    OAuthConnectionTokenService,
)

_CONNECTION_ID = uuid4()
_CREDENTIAL_STORE = object()
_ACCOUNT_ID = "acct-1"
_FAR_FUTURE_MS = int((time.time() + 3600) * 1000)


class _FakeStore:
    def __init__(self, connection) -> None:  # noqa: ANN001
        self.connection = connection
        self.last_refreshed_touches = 0
        self.last_used_touches = 0
        self.error_marks = 0

    async def get(self, account_id, connection_id):  # noqa: ANN001
        assert account_id == _ACCOUNT_ID
        assert connection_id == self.connection.id
        return self.connection

    async def mark_error(self, connection, message: str):  # noqa: ANN001
        self.error_marks += 1
        connection.status = "error"
        connection.error_message = message
        return connection

    async def touch_last_refreshed(self, connection):  # noqa: ANN001
        self.last_refreshed_touches += 1
        return connection

    async def touch_last_used(self, connection):  # noqa: ANN001
        self.last_used_touches += 1
        return connection


class _SharedRefreshStrategy:
    """Lock-bearing fake mirroring ``BaseOAuthStrategy``'s locked, once-only
    refresh across BOTH the token path (``get_token_with_expiry``) and the chat
    path (``get_authorization_header``) — see ``core/oauth_base.py:56-89``.

    It starts COLD (``_cached is None``) on purpose: the real
    ``get_authorization_header`` has a lock-free fast path
    (``core/oauth_base.py:80``) that returns an *already-valid* token without
    taking the lock. A warm start would let the chat path short-circuit and the
    test could prove cache identity without ever proving token↔chat refresh
    contention (a false positive). Cold start forces every first refresh through
    the shared lock. Both methods refresh via ``_refresh_locked`` so
    ``max_concurrent_refresh`` is the true cross-path concurrency of the refresh.
    """

    def __init__(self, *, refresh_error: Exception | None = None) -> None:
        self._lock = asyncio.Lock()
        self._cached: dict | None = None
        self._refresh_error = refresh_error
        self.refreshes = 0
        self._active = 0
        self.max_concurrent_refresh = 0

    async def _refresh_locked(self) -> None:
        # Invariant under test: this only ever runs while holding self._lock.
        self._active += 1
        self.max_concurrent_refresh = max(self.max_concurrent_refresh, self._active)
        try:
            await asyncio.sleep(0.02)  # widen the window so a real race would overlap
            if self._refresh_error is not None:
                raise self._refresh_error
            self.refreshes += 1
            self._cached = {
                "access_token": f"tok-{self.refreshes}",
                "expires_at_ms": _FAR_FUTURE_MS,
            }
        finally:
            self._active -= 1

    async def get_token_with_expiry(self) -> tuple[str, int, bool]:
        refreshed = False
        async with self._lock:
            if self._cached is None:
                await self._refresh_locked()
                refreshed = True
        assert self._cached is not None  # a successful _refresh_locked always populates it
        return self._cached["access_token"], int(self._cached["expires_at_ms"]), refreshed

    async def get_authorization_header(self) -> dict[str, str]:
        async with self._lock:
            if self._cached is None:
                await self._refresh_locked()
        assert self._cached is not None  # a successful _refresh_locked always populates it
        return {"Authorization": f"Bearer {self._cached['access_token']}"}


class _FakePlugin:
    """Builds a NEW lock-bearing strategy on every call and counts builds, so a
    test can prove the *cache* (not this plugin) is what shares the instance."""

    def __init__(self, *, refresh_error: Exception | None = None) -> None:
        self.builds = 0
        self.built: list[_SharedRefreshStrategy] = []
        self._refresh_error = refresh_error

    def oauth_strategy_for(self, profile_name: str, **kwargs):  # noqa: ANN003
        assert profile_name.endswith(str(_CONNECTION_ID))
        assert kwargs["credential_store"] is _CREDENTIAL_STORE
        self.builds += 1
        strategy = _SharedRefreshStrategy(refresh_error=self._refresh_error)
        self.built.append(strategy)
        return strategy


class _FakeProviders:
    def __init__(self, plugin: _FakePlugin) -> None:
        self._plugin = plugin

    def get(self, provider: str):
        assert provider == "anthropic"
        return self._plugin


def _active_connection() -> SimpleNamespace:
    # No auth_type attr -> getattr(..., "oauth") -> treated as an OAuth connection.
    return SimpleNamespace(id=_CONNECTION_ID, provider="anthropic", status="active")


def _token_call(service, cache, plugin, store):  # noqa: ANN001
    return service.get_token(
        account_id=_ACCOUNT_ID,
        connection_id=_CONNECTION_ID,
        store=store,
        providers=_FakeProviders(plugin),
        credential_store=_CREDENTIAL_STORE,
        http_client_factory_for=lambda _provider: None,
        strategy_cache=cache,
    )


def _chat_build(plugin: _FakePlugin):
    return plugin.oauth_strategy_for(
        credential_key_for(_ACCOUNT_ID, _CONNECTION_ID),
        credential_store=_CREDENTIAL_STORE,
        http_client_factory=None,
    )


async def _chat_call(cache: CredentialStrategyCache, plugin: _FakePlugin) -> None:
    # Mirrors routes/chat.py:_strategy_for_credential_target — the *identical*
    # cache key the token service now uses, then the chat-dispatch entry point.
    strategy = cache.get_or_create(
        provider="anthropic",
        auth_type="oauth",
        credential_name=credential_key_for(_ACCOUNT_ID, _CONNECTION_ID),
        build=lambda: _chat_build(plugin),
    )
    await strategy.get_authorization_header()


@pytest.mark.asyncio
async def test_token_service_serializes_refresh_for_same_connection() -> None:
    # Two concurrent token requests share ONE cached strategy, so exactly one
    # refresh happens (single-flight). The cache — not a shared test double — is
    # what makes them share: the plugin builds a fresh strategy per call.
    cache = CredentialStrategyCache()
    plugin = _FakePlugin()
    store = _FakeStore(_active_connection())
    service = OAuthConnectionTokenService()

    first, second = await asyncio.gather(
        _token_call(service, cache, plugin, store),
        _token_call(service, cache, plugin, store),
    )

    assert plugin.builds == 1, "the shared cache must build the strategy exactly once"
    assert len(plugin.built) == 1
    shared = plugin.built[0]
    assert shared.refreshes == 1, "exactly one refresh across both token calls (single-flight)"
    assert shared.max_concurrent_refresh == 1, "no concurrent refresh"
    # Both callers observe the same freshly-refreshed token.
    assert first.access_token == second.access_token == "tok-1"
    assert first.refreshed != second.refreshed, "exactly one caller performed the refresh"
    # Only the refreshing caller touches last_refreshed; both touch last_used.
    assert store.last_refreshed_touches == 1
    assert store.last_used_touches == 2


@pytest.mark.asyncio
async def test_token_and_chat_paths_single_flight_through_shared_cache() -> None:
    # AC2 / AC3 deliverable: the token endpoint (get_token_with_expiry) and chat
    # dispatch (get_authorization_header) for the same connection must resolve ONE
    # strategy instance and refresh it exactly once, even when interleaved.
    cache = CredentialStrategyCache()
    plugin = _FakePlugin()
    store = _FakeStore(_active_connection())
    service = OAuthConnectionTokenService()

    await asyncio.gather(
        _token_call(service, cache, plugin, store),
        _chat_call(cache, plugin),
        _token_call(service, cache, plugin, store),
        _chat_call(cache, plugin),
    )

    assert plugin.builds == 1, "token and chat must land on one cached instance, not two"
    assert len(plugin.built) == 1
    shared = plugin.built[0]
    assert shared.refreshes == 1, "single-flight across BOTH the token and chat paths"
    assert shared.max_concurrent_refresh == 1, "token↔chat refresh never overlaps"


@pytest.mark.asyncio
async def test_concurrent_failing_refresh_never_overlaps() -> None:
    # Removing the token-service outer lock means two already-in-flight callers
    # can each surface an error and each mark the connection errored — that is the
    # documented, accepted trade-off (SF-323 plan §3). The invariant that still
    # MUST hold is that the doomed refreshes never run concurrently against the
    # provider (no 429 refresh_token_conflict).
    cache = CredentialStrategyCache()
    plugin = _FakePlugin(refresh_error=ReauthRequiredError("refresh token revoked"))
    store = _FakeStore(_active_connection())
    service = OAuthConnectionTokenService()

    results = await asyncio.gather(
        _token_call(service, cache, plugin, store),
        _token_call(service, cache, plugin, store),
        return_exceptions=True,
    )

    assert plugin.builds == 1
    shared = plugin.built[0]
    assert shared.refreshes == 0, "a failing refresh never records a success"
    assert shared.max_concurrent_refresh == 1, "refresh attempts are serialized, never concurrent"
    # Narrow inside one comprehension so the type checker sees status_code, and
    # so each result is asserted to be BOTH the error type AND a 401 together.
    assert all(isinstance(r, OAuthConnectionTokenError) and r.status_code == 401 for r in results)
    # Both in-flight callers reached mark_error before the first status flip was
    # visible; the store must tolerate the duplicate marking.
    assert store.error_marks == 2


@pytest.mark.asyncio
async def test_transient_refresh_failure_maps_to_503_without_marking_error() -> None:
    # AuthError (transient upstream 5xx) leaves the connection active so callers
    # back off and retry; it must NOT mark the connection errored.
    cache = CredentialStrategyCache()
    plugin = _FakePlugin(refresh_error=AuthError("provider 503"))
    store = _FakeStore(_active_connection())
    service = OAuthConnectionTokenService()

    with pytest.raises(OAuthConnectionTokenError) as excinfo:
        await _token_call(service, cache, plugin, store)

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail["code"] == "upstream_refresh_failed"
    assert store.error_marks == 0


@pytest.mark.asyncio
async def test_without_shared_cache_each_path_refreshes_independently() -> None:
    # Contrast / regression guard: the OLD token-path behavior (a fresh strategy
    # per call, NOT shared with chat) refreshes the rotating token twice — the
    # SF-323 bug. Mirrors test_credential_strategy_cache.py::
    # test_without_cache_each_request_refreshes_independently.
    plugin = _FakePlugin()

    async def token_like() -> None:
        await plugin.oauth_strategy_for(
            credential_key_for(_ACCOUNT_ID, _CONNECTION_ID),
            credential_store=_CREDENTIAL_STORE,
        ).get_token_with_expiry()

    async def chat_like() -> None:
        await plugin.oauth_strategy_for(
            credential_key_for(_ACCOUNT_ID, _CONNECTION_ID),
            credential_store=_CREDENTIAL_STORE,
        ).get_authorization_header()

    await asyncio.gather(token_like(), chat_like())

    assert plugin.builds == 2
    assert sum(s.refreshes for s in plugin.built) == 2, "unshared strategies each refresh (the bug)"
