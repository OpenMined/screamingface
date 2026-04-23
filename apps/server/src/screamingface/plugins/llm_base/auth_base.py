"""AuthStrategy ABC — how to build the Authorization header for a provider call.

Each provider plugin implements one or more concrete
:class:`AuthStrategy` subclasses. For example, ``claude_backend_api``
will provide:

- ``ClaudeCodeOAuth`` — reads the OAuth token Claude Code stores in the
  platform credential store, refreshes it proactively, and returns a
  ``Bearer`` header.
- (future) ``AnthropicApiKeyAuth`` — reads an API key from settings or
  env var and returns an ``x-api-key`` header. Alternate flow for users
  who don't want a CLI dependency.

The ABC exposes two async methods: :meth:`get_authorization_header`
(called on every outbound request) and :meth:`refresh` (called when an
access token expires).

Concurrency note: implementations that cache tokens MUST protect the
refresh path with an ``asyncio.Lock`` so two concurrent coroutines
don't both fire a refresh and race on the credential store.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AuthStrategy(ABC):
    """Abstract contract for building provider auth headers."""

    @abstractmethod
    async def get_authorization_header(self) -> dict[str, str]:
        """Return the headers the backend should include on the outbound call.

        Typically returns ``{"Authorization": "Bearer <token>"}`` for
        OAuth-based strategies or ``{"x-api-key": "<key>"}`` for API-key
        strategies. Implementations may return additional provider-
        specific headers (e.g. ``anthropic-beta`` for OAuth-authenticated
        Anthropic calls).

        Implementations must handle cache-and-refresh internally. Callers
        should not have to know whether a refresh happened.

        Raises:
            CredentialNotFoundError: The credential doesn't exist and
                the user needs to run their CLI login command.
            AuthError: The credential exists but is broken (refresh
                failed, scope rejected, etc.) and the user must
                re-authenticate.
        """

    @abstractmethod
    async def refresh(self) -> None:
        """Force-refresh the cached credential.

        Used by :meth:`get_authorization_header` internally and by the
        Phase 5 UI's ``POST /backends/<name>/refresh`` endpoint.

        Implementations should acquire their internal lock before
        touching the credential cache, perform the refresh round-trip,
        update the in-memory cache, and write back to the credential
        store.

        Raises:
            AuthError: Refresh failed in a way the user must fix
                (refresh token expired, invalid_grant, etc.).
        """

    def invalidate_cache(self) -> None:
        """Drop any cached credential so the next
        :meth:`get_authorization_header` forces a fresh read or refresh.

        Default is a no-op — strategies that don't cache (e.g. plain
        API-key readers) inherit this trivially. OAuth strategies
        override to clear their in-memory cache *and* the credential
        store entry if it's detectably stale.

        Called by the shared POST-with-retry helper when the provider
        returns 401, under the assumption that the cached token went
        bad mid-request (rare race with a concurrent refresh).
        """
