from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from aigateway.core.oauth.token_service import OAuthConnectionTokenService


class _FakeStore:
    def __init__(self, connection) -> None:  # noqa: ANN001
        self.connection = connection
        self.last_refreshed_touches = 0
        self.last_used_touches = 0

    async def get(self, account_id, connection_id):  # noqa: ANN001
        assert account_id == "acct-1"
        assert connection_id == self.connection.id
        return self.connection

    async def mark_error(self, connection, message: str):  # noqa: ANN001
        connection.status = "error"
        connection.error_message = message
        return connection

    async def touch_last_refreshed(self, connection):  # noqa: ANN001
        self.last_refreshed_touches += 1
        return connection

    async def touch_last_used(self, connection):  # noqa: ANN001
        self.last_used_touches += 1
        return connection


class _FakeStrategy:
    active_calls = 0
    max_active_calls = 0
    total_calls = 0

    async def get_token_with_expiry(self) -> tuple[str, int, bool]:
        type(self).active_calls += 1
        type(self).total_calls += 1
        type(self).max_active_calls = max(type(self).max_active_calls, type(self).active_calls)
        try:
            await asyncio.sleep(0.02)
            return (
                f"token-{type(self).total_calls}",
                int((time.time() + 3600) * 1000),
                True,
            )
        finally:
            type(self).active_calls -= 1


class _FakePlugin:
    def oauth_strategy_for(self, profile_name: str, **kwargs):  # noqa: ANN003
        assert profile_name.endswith(str(_CONNECTION_ID))
        assert kwargs["credential_store"] is _CREDENTIAL_STORE
        return _FakeStrategy()


class _FakeProviders:
    def get(self, provider: str):
        assert provider == "anthropic"
        return _FakePlugin()


_CONNECTION_ID = uuid4()
_CREDENTIAL_STORE = object()


@pytest.mark.asyncio
async def test_token_service_serializes_refresh_for_same_connection() -> None:
    _FakeStrategy.active_calls = 0
    _FakeStrategy.max_active_calls = 0
    _FakeStrategy.total_calls = 0
    connection = SimpleNamespace(id=_CONNECTION_ID, provider="anthropic", status="active")
    store = _FakeStore(connection)
    service = OAuthConnectionTokenService()

    first, second = await asyncio.gather(
        service.get_token(
            account_id="acct-1",
            connection_id=_CONNECTION_ID,
            store=store,
            providers=_FakeProviders(),
            credential_store=_CREDENTIAL_STORE,
            http_client_factory_for=lambda _provider: None,
        ),
        service.get_token(
            account_id="acct-1",
            connection_id=_CONNECTION_ID,
            store=store,
            providers=_FakeProviders(),
            credential_store=_CREDENTIAL_STORE,
            http_client_factory_for=lambda _provider: None,
        ),
    )

    assert {first.access_token, second.access_token} == {"token-1", "token-2"}
    assert _FakeStrategy.total_calls == 2
    assert _FakeStrategy.max_active_calls == 1
    assert store.last_refreshed_touches == 2
    assert store.last_used_touches == 2
