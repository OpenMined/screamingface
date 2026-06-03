"""AigwTokenSource — fetch + cache OAuth tokens from aigateway.

Plugged into OAuthStrategy._read_credential / _refresh_credential when a
backend plugin has connection_id + aigw_url configured. Aigateway handles
provider-side refresh; this helper just trusts the access_token + expires_at
it gets back and caches in-memory until 30s before expiry.

Critical: aigateway is NOT on the LLM hot path. We fetch a fresh token,
then call the LLM provider directly. Aigateway availability affects auth,
not chat completions.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_REFRESH_WINDOW = timedelta(seconds=30)
_DEFAULT_TIMEOUT = 5.0


class AigwTokenError(Exception):
    """Aigateway returned a non-recoverable status (404/503/transport)."""


class AigwAuthError(AigwTokenError):
    """Aigateway returned 401 — the caller's JWT is invalid / expired."""


@dataclass
class _CacheEntry:
    access_token: str
    expires_at: datetime


class AigwTokenSource:
    """Fetch + cache aigateway access tokens for one connection.

    Args:
        connection_id: aigateway OAuthConnection id.
        aigw_url: aigateway base URL (e.g. http://localhost:9105).
        aigw_jwt_provider: async getter for the current aigw JWT. Called
            on every fetch so re-login picks up automatically.
        http_timeout: per-request timeout in seconds. Default 5s.
        http_transport: injected by tests (httpx.MockTransport).
    """

    def __init__(
        self,
        *,
        connection_id: str,
        aigw_url: str,
        aigw_jwt_provider: Callable[[], Awaitable[str]],
        http_timeout: float = _DEFAULT_TIMEOUT,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._connection_id = connection_id
        self._aigw_url = aigw_url.rstrip("/")
        self._jwt_provider = aigw_jwt_provider
        self._timeout = http_timeout
        self._transport = http_transport
        self._cache: _CacheEntry | None = None
        self._lock = asyncio.Lock()

    async def fetch_token(self) -> str:
        async with self._lock:
            now = datetime.now(UTC)
            if self._cache is not None and self._cache.expires_at - now > _REFRESH_WINDOW:
                return self._cache.access_token
            entry = await self._fetch_once()
            self._cache = entry
            return entry.access_token

    def invalidate_cache(self) -> None:
        self._cache = None

    @property
    def connection_id(self) -> str:
        return self._connection_id

    async def _fetch_once(self) -> _CacheEntry:
        jwt = await self._jwt_provider()
        url = f"{self._aigw_url}/v1/oauth/connections/{self._connection_id}/token"
        client_kwargs: dict = {"timeout": self._timeout}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        headers = {"Authorization": f"Bearer {jwt}"} if jwt else {}
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise AigwTokenError(f"aigw unreachable at {url}: {exc}") from exc

        if resp.status_code == 401:
            raise AigwAuthError("aigateway rejected the JWT — re-login to aigateway required.")
        if resp.status_code != 200:
            raise AigwTokenError(
                f"aigateway returned {resp.status_code} for connection "
                f"{self._connection_id}: {resp.text[:200]}"
            )
        data = resp.json()
        try:
            expires_at = datetime.fromisoformat(data["expires_at"])
        except (KeyError, ValueError) as exc:
            raise AigwTokenError(
                f"aigateway response missing or malformed 'expires_at': {data!r}"
            ) from exc
        if "access_token" not in data:
            raise AigwTokenError(f"aigateway response missing 'access_token': {data!r}")
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return _CacheEntry(access_token=data["access_token"], expires_at=expires_at)


async def aigw_jwt_from_env() -> str:
    """Default JWT provider — reads SF_AIGW_JWT from the environment.

    Bootstrap path until DEMO-029 (desktop session manager) wires a
    real IPC-driven provider. If the env var is unset, the helper
    raises AigwAuthError so the failure surfaces as 'aigw JWT missing'
    rather than a 401 round-trip.
    """
    jwt = os.environ.get("SF_AIGW_JWT", "").strip()
    if not jwt:
        raise AigwAuthError("SF_AIGW_JWT is not set — log in to aigateway or unset connection_id.")
    return jwt


async def aigw_jwt_from_gateway_session(app: Any) -> str:
    """JWT provider for SF's in-memory Desktop -> AIGateway session."""

    from screamingface.plugins.aigw_base.config import resolve_aigw_runtime_config

    if resolve_aigw_runtime_config(app).mode == "local_managed":
        return ""

    app_state = getattr(app, "state", None)
    if app_state is not None:
        from screamingface.plugins.aigw_base.client import gateway_session_state

        token = gateway_session_state(app).valid_token()
        if token:
            return token

    jwt = os.environ.get("SF_AIGW_JWT", "").strip()
    if jwt:
        return jwt
    raise AigwAuthError(
        "AIGateway session is missing or expired — sign in from Desktop or set SF_AIGW_JWT."
    )


def aigw_jwt_provider_for_app(app: Any | None) -> Callable[[], Awaitable[str]]:
    """Return the best JWT provider for a provider plugin instance."""

    if app is None:
        return aigw_jwt_from_env

    async def _provider() -> str:
        return await aigw_jwt_from_gateway_session(app)

    return _provider


__all__ = [
    "AigwTokenSource",
    "AigwTokenError",
    "AigwAuthError",
    "aigw_jwt_from_env",
    "aigw_jwt_from_gateway_session",
    "aigw_jwt_provider_for_app",
]
