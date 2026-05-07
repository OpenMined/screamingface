"""Template-method base for OAuth-backed credential strategies.

Owns the shared flow: in-memory cache, double-checked locking with an
asyncio.Lock, proactive refresh inside the lock, 401-driven invalidation.
Provider plugins implement four hooks: read, is_expired, refresh,
build_headers (plus an optional header_override for hybrid api-key paths).
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod

from .plugin_base import OAuthStrategy


class BaseOAuthStrategy(OAuthStrategy):
    """Cached, locked, proactively-refreshed OAuth strategy.

    `refresh_window_seconds` controls how long before actual expiry a
    refresh kicks in. 60s matches what Claude Code, Codex CLI, and Gemini
    CLI all do.
    """

    refresh_window_seconds: int = 60

    def __init__(self, profile_name: str) -> None:
        self.profile_name = profile_name
        self._cached: dict | None = None
        self._lock = asyncio.Lock()

    async def get_authorization_header(self) -> dict[str, str]:
        override = self._header_override()
        if override is not None:
            return override

        if self._cached is not None and not self._is_expired(self._cached):
            return self._build_headers(self._cached)

        async with self._lock:
            if self._cached is None:
                self._cached = self._read_credential()
            if self._is_expired(self._cached):
                self._cached = await self._refresh_credential(self._cached)

        return self._build_headers(self._cached)

    async def invalidate(self) -> None:
        self._cached = None

    async def refresh(self) -> None:
        async with self._lock:
            if self._cached is None:
                self._cached = self._read_credential()
            self._cached = await self._refresh_credential(self._cached)

    def set_credentials(self, creds: dict) -> None:
        """Store a credential blob (used after callback's code-for-token exchange)."""
        self._cached = creds
        self._write_to_store(creds)

    @abstractmethod
    def keychain_service(self) -> str:
        """OS keychain `service` string for this profile's tokens."""

    @abstractmethod
    def keychain_account(self) -> str:
        """OS keychain `account` string for this profile's tokens."""

    @abstractmethod
    def _write_to_store(self, creds: dict) -> None:
        """Persist `creds` to the OS keychain entry."""

    def _header_override(self) -> dict[str, str] | None:
        """Override to short-circuit OAuth (e.g. when an API-key env var is set)."""
        return None

    @abstractmethod
    def _read_credential(self) -> dict: ...

    @abstractmethod
    def _is_expired(self, creds: dict) -> bool: ...

    @abstractmethod
    async def _refresh_credential(self, creds: dict) -> dict: ...

    @abstractmethod
    def _build_headers(self, creds: dict) -> dict[str, str]: ...
