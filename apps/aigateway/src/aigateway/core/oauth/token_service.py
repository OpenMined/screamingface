from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

from aigateway.core.errors import AuthError, CredentialNotFoundError, ReauthRequiredError
from aigateway.core.oauth.models import OAuthConnection
from aigateway.core.oauth.store import credential_key_for


class OAuthConnectionStoreLike(Protocol):
    async def get(self, account_id: str | UUID, connection_id: UUID) -> Any | None: ...

    async def mark_error(self, connection: Any, message: str) -> Any: ...

    async def touch_last_refreshed(self, connection: Any) -> Any: ...

    async def touch_last_used(self, connection: Any) -> Any: ...


class ProviderRegistryLike(Protocol):
    def get(self, provider: str) -> Any | None: ...


class TokenWithExpiryStrategy(Protocol):
    async def get_token_with_expiry(self) -> tuple[str, int, bool]: ...


@dataclass(frozen=True)
class OAuthConnectionToken:
    connection: OAuthConnection
    access_token: str
    expires_at_ms: int
    refreshed: bool


class OAuthConnectionTokenError(Exception):
    def __init__(self, status_code: int, detail: dict[str, Any]) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class OAuthConnectionTokenService:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def get_token(
        self,
        *,
        account_id: str | UUID,
        connection_id: UUID,
        store: OAuthConnectionStoreLike,
        providers: ProviderRegistryLike,
        credential_store: Any,
        http_client_factory_for,
    ) -> OAuthConnectionToken:
        lock = await self._lock_for(account_id, connection_id)
        async with lock:
            return await self._get_token_locked(
                account_id=account_id,
                connection_id=connection_id,
                store=store,
                providers=providers,
                credential_store=credential_store,
                http_client_factory_for=http_client_factory_for,
            )

    async def _get_token_locked(
        self,
        *,
        account_id: str | UUID,
        connection_id: UUID,
        store: OAuthConnectionStoreLike,
        providers: ProviderRegistryLike,
        credential_store: Any,
        http_client_factory_for,
    ) -> OAuthConnectionToken:
        connection = await store.get(account_id, connection_id)
        if connection is None:
            raise OAuthConnectionTokenError(404, {"code": "connection_not_found"})
        if connection.status != "active":
            raise OAuthConnectionTokenError(409, {"code": "connection_not_active"})

        plugin = providers.get(connection.provider)
        if plugin is None:
            raise OAuthConnectionTokenError(404, {"code": "unknown_provider"})
        strategy = plugin.oauth_strategy_for(
            credential_key_for(account_id, connection.id),
            credential_store=credential_store,
            http_client_factory=http_client_factory_for(connection.provider),
        )
        if strategy is None:
            raise OAuthConnectionTokenError(400, {"code": "provider_does_not_use_oauth"})
        token_strategy = cast(TokenWithExpiryStrategy, strategy)

        try:
            access_token, expires_at_ms, refreshed = await token_strategy.get_token_with_expiry()
        except (CredentialNotFoundError, ReauthRequiredError) as exc:
            # Credential missing, or the refresh token was rejected by the provider
            # (revoked / invalid_grant). The connection cannot recover without a new
            # browser auth, so mark it errored and tell the caller to re-auth.
            await store.mark_error(connection, str(exc))
            raise OAuthConnectionTokenError(
                401, {"code": "auth_required", "message": str(exc)}
            ) from exc
        except AuthError as exc:
            # Transient upstream refresh failure (network error, provider 5xx). Leave
            # the connection active and surface 503 so callers back off and retry.
            raise OAuthConnectionTokenError(
                503, {"code": "upstream_refresh_failed", "message": str(exc)}
            ) from exc

        if refreshed:
            await store.touch_last_refreshed(connection)
        await store.touch_last_used(connection)
        return OAuthConnectionToken(
            connection=connection,
            access_token=access_token,
            expires_at_ms=expires_at_ms,
            refreshed=refreshed,
        )

    async def _lock_for(self, account_id: str | UUID, connection_id: UUID) -> asyncio.Lock:
        key = f"{account_id}:{connection_id}"
        async with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock


def oauth_connection_token_service(app: Any) -> OAuthConnectionTokenService:
    state = getattr(app, "state", None)
    if state is None:
        raise RuntimeError("AIGateway app state is unavailable")
    service = getattr(state, "oauth_connection_token_service", None)
    if not isinstance(service, OAuthConnectionTokenService):
        service = OAuthConnectionTokenService()
        state.oauth_connection_token_service = service
    return service
