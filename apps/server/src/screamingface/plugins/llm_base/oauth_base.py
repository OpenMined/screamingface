"""OAuthStrategy — Template-Method base for every OAuth-backed AuthStrategy.

Before this module existed, ClaudeCodeOAuth, CodexOAuth, and GeminiAuth
each hand-rolled the same five-step flow:

1. Cache the credential in memory.
2. On every outbound request, check the cache and return headers if
   still fresh.
3. If expired / missing, acquire an ``asyncio.Lock``, re-read from the
   credential store, and run a refresh POST (double-checked locking).
4. On success, write the refreshed credential back.
5. On 401 from the backend, drop the cache so the next call re-reads.

The flow itself is identical across providers. What differs is:

- Where the credential lives (macOS keychain, JSON file on disk, …).
- How "expired" is computed (``expiresAt`` ms field vs JWT ``exp``).
- What the refresh POST body and response shapes look like.
- What the final ``Authorization`` headers are.

:class:`OAuthStrategy` owns the flow and exposes four abstract hooks
for the provider-specific pieces. Subclasses shrink from ~300 lines
to ~100.

Hybrid strategies (e.g. Gemini supports API-key OR OAuth) override
:meth:`_header_override` to short-circuit the OAuth path when an
API-key env var is present.
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from datetime import UTC, datetime

from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
from screamingface.plugins.llm_base.auth_base import AuthStrategy


class OAuthStrategy(AuthStrategy):
    """Cached + locked + proactively-refreshed OAuth strategy base.

    Attributes:
        refresh_window_seconds: How many seconds before actual expiry
            the strategy should proactively refresh. 60s matches the
            behavior of Claude Code, Codex CLI, and Gemini CLI.
    """

    refresh_window_seconds: int = 60

    def __init__(self, *, aigw_source: AigwTokenSource | None = None) -> None:
        self._cached: dict | None = None
        self._lock = asyncio.Lock()
        self._aigw_source = aigw_source

    # ------------------------------------------------------------------
    # AuthStrategy implementation — the shared flow
    # ------------------------------------------------------------------

    async def get_authorization_header(self) -> dict[str, str]:
        override = self._header_override()
        if override is not None:
            return override

        # Fast path: cache hit, still fresh.
        if self._cached is not None and not self._is_expired(self._cached):
            return self._build_headers(self._cached)

        # Slow path: read + maybe refresh under lock.
        async with self._lock:
            # Double-check inside the lock: another coroutine may have
            # refreshed while we were waiting.
            if self._cached is None:
                self._cached = await self._load_credential()
            if self._is_expired(self._cached):
                self._cached = await self._refresh_or_aigw(self._cached)

        return self._build_headers(self._cached)

    async def refresh(self) -> None:
        """Force a refresh regardless of cached expiry."""
        async with self._lock:
            if self._cached is None:
                self._cached = await self._load_credential()
            self._cached = await self._refresh_or_aigw(self._cached)

    def invalidate_cache(self) -> None:
        """Drop in-memory state. The next header build re-reads the store."""
        self._cached = None

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    async def _load_credential(self) -> dict:
        if self._aigw_source is not None:
            return await self._fetch_via_aigw()
        return self._read_credential()

    async def _refresh_or_aigw(self, creds: dict) -> dict:
        if self._aigw_source is not None:
            return await self._fetch_via_aigw()
        return await self._refresh_credential(creds)

    async def _fetch_via_aigw(self) -> dict:
        assert self._aigw_source is not None
        token = await self._aigw_source.fetch_token()
        placeholder_expiry = datetime.now(UTC).replace(microsecond=0)
        return self._aigw_creds_shape(token, placeholder_expiry)

    def _aigw_creds_shape(self, access_token: str, expires_at: datetime) -> dict:
        """Translate aigw token response → provider-shaped creds dict.

        Default raises — providers must opt in by overriding this method.
        The shape returned must satisfy _build_headers (and _is_expired,
        though _is_expired is bypassed on the aigw path).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support aigw_source — set connection_id only "
            "on a provider that has implemented _aigw_creds_shape."
        )

    def _header_override(self) -> dict[str, str] | None:
        """Return non-OAuth headers if the strategy has a short-circuit.

        Default: ``None`` (always go through the OAuth flow).

        Hybrid strategies (e.g. Gemini with ``GEMINI_API_KEY``) override
        to return an API-key header when the env var is present, bypassing
        the cache + refresh machinery entirely.
        """
        return None

    @abstractmethod
    def _read_credential(self) -> dict:
        """Load the raw credential dict from the provider's on-disk store.

        Raises:
            CredentialNotFoundError: No credential present — user must run
                the provider's CLI login command.
            AuthError: Credential present but malformed.
        """

    @abstractmethod
    def _is_expired(self, creds: dict) -> bool:
        """True if the credential is within the refresh window."""

    @abstractmethod
    async def _refresh_credential(self, creds: dict) -> dict:
        """POST to the provider's refresh endpoint, write back, return the
        new credential dict. Must be called under ``self._lock``.

        Raises:
            AuthError: Refresh failed in a way the user must fix.
        """

    @abstractmethod
    def _build_headers(self, creds: dict) -> dict[str, str]:
        """Build the outbound HTTP headers from a validated credential."""
