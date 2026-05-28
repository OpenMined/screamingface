"""Template-method base for OAuth-backed credential strategies.

Owns the shared flow: in-memory cache, double-checked locking with an
asyncio.Lock, proactive refresh inside the lock, 401-driven invalidation.
Provider plugins implement four hooks: read, is_expired, refresh,
build_headers (plus an optional header_override for hybrid api-key paths).
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from .plugin_base import OAuthStrategy

if TYPE_CHECKING:
    from .credential_blob.store import CredentialBlobStore


class BaseOAuthStrategy(OAuthStrategy):
    """Cached, locked, proactively-refreshed OAuth strategy.

    `refresh_window_seconds` controls how long before actual expiry a
    refresh kicks in. 60s matches what Claude Code, Codex CLI, and Gemini
    CLI all do.
    """

    refresh_window_seconds: int = 60
    _store: CredentialBlobStore

    def __init__(self, profile_name: str) -> None:
        self.profile_name = profile_name
        self._cached: dict | None = None
        self._lock = asyncio.Lock()

    async def get_token_with_expiry(self) -> tuple[str, int]:
        """Return (access_token, expires_at_ms), refreshing if needed.

        Used by GET /v1/oauth/connections/{id}/token. All three providers
        (anthropic, codex, gemini) normalize creds to {access_token,
        expires_at_ms} in _read_credential / _refresh_credential, so a
        base-class implementation is correct for every concrete subclass.
        """
        async with self._lock:
            if self._cached is None:
                self._cached = self._read_credential()
            if self._is_expired(self._cached):
                self._cached = await self._refresh_credential(self._cached)
        return self._cached["access_token"], int(self._cached["expires_at_ms"])

    async def get_authorization_header(self) -> dict[str, str]:
        override = self._header_override()
        if override is not None:
            return override

        if self._cached is not None and not self._is_expired(self._cached):
            return self._build_headers(self._cached)

        async with self._lock:
            if self._cached is None:
                self._cached = await self._read_credential()
            if self._is_expired(self._cached):
                self._cached = await self._refresh_credential(self._cached)

        return self._build_headers(self._cached)

    async def invalidate(self) -> None:
        self._cached = None

    async def refresh(self) -> None:
        async with self._lock:
            if self._cached is None:
                self._cached = await self._read_credential()
            self._cached = await self._refresh_credential(self._cached)

    async def persist_credentials(self, credentials: dict[str, Any]) -> None:
        """Store a credential blob after callback's code-for-token exchange."""
        self._cached = credentials
        await self._write_to_store(credentials)

    async def delete_credentials(self) -> None:
        self._cached = None
        await self._store.delete(self.credential_service(), self.credential_account())

    async def refresh_credentials(self) -> None:
        await self.refresh()

    @abstractmethod
    def credential_service(self) -> str:
        """Credential blob `service` string for this profile's tokens."""

    @abstractmethod
    def credential_account(self) -> str:
        """Credential blob `account` string for this profile's tokens."""

    @abstractmethod
    async def _write_to_store(self, creds: dict[str, Any]) -> None:
        """Persist `creds` to the credential blob store."""

    def _header_override(self) -> dict[str, str] | None:
        """Override to short-circuit OAuth (e.g. when an API-key env var is set)."""
        return None

    @abstractmethod
    async def _read_credential(self) -> dict[str, Any]: ...

    @abstractmethod
    def _is_expired(self, creds: dict[str, Any]) -> bool: ...

    @abstractmethod
    async def _refresh_credential(self, creds: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def _build_headers(self, creds: dict[str, Any]) -> dict[str, str]: ...
