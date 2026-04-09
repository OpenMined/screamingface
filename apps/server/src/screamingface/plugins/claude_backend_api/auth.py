"""Claude Code OAuth auth strategy — reads the token from the credential store.

Every detail here was validated by the SF-77 spike
(``apps/server/scripts/oauth_spike.py``,
``apps/server/docs/oauth-spike-findings.md``). Do not change without
re-running the spike or at least understanding the spike's findings.

The flow:

1. Read the JSON credential from the credential store at service name
   ``"Claude Code-credentials"``. This is where Claude Code's
   ``claude auth login`` command writes.
2. Parse the JSON, extract ``claudeAiOauth.{accessToken, refreshToken,
   expiresAt, scopes, subscriptionType}``.
3. If ``expiresAt`` is within 60 seconds of now, proactively refresh by
   POSTing to ``https://console.anthropic.com/v1/oauth/token`` with
   ``{grant_type: "refresh_token", refresh_token, client_id}``.
4. Convert the refresh response (snake_case, ``expires_in`` seconds) to
   the keychain shape (camelCase, ``expiresAt`` ms) and write back to
   the credential store.
5. Build the outbound headers for ``/v1/messages`` calls:
   - ``Authorization: Bearer <accessToken>``
   - ``anthropic-version: 2023-06-01``
   - ``anthropic-beta: oauth-2025-04-20``  (REQUIRED — without it the
     scope check rejects even a valid token)

Concurrency: a per-instance asyncio.Lock protects the refresh path so
two concurrent coroutines don't both fire a refresh and race on the
credential store. Uses double-checked locking to avoid unnecessary lock
acquisition on the common (cache-hit) path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import httpx

from screamingface.plugins.llm_base.auth_base import AuthStrategy
from screamingface.plugins.llm_base.credential_store import (
    CredentialStore,
    get_credential_store,
)
from screamingface.plugins.llm_base.errors import AuthError, CredentialNotFoundError

logger = logging.getLogger(__name__)

# These constants are the load-bearing values validated by the SF-77 spike.
KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_REFRESH_URL = "https://console.anthropic.com/v1/oauth/token"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # public Claude Code OAuth app
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_BETA = "oauth-2025-04-20"  # REQUIRED on every call with an OAuth bearer

# Proactive refresh window — refresh when the token has less than this
# many seconds of validity remaining. 60s matches the plan's locked-in
# decision and mirrors Claude Code's own behavior.
REFRESH_WINDOW_SECONDS = 60


class ClaudeCodeOAuth(AuthStrategy):
    """Reads Claude Code's OAuth token from the platform credential store.

    Args:
        credential_store: The credential store to read from. Defaults to
            whatever ``get_credential_store()`` returns for the current
            platform. Tests can inject a fake store here.
        account: The account name to look up. Defaults to the ``USER``
            env var (which is what Claude Code writes).
        http_client_factory: Callable returning a new ``httpx.AsyncClient``.
            Tests can inject a factory that returns a mocked client.
    """

    def __init__(
        self,
        *,
        credential_store: CredentialStore | None = None,
        account: str | None = None,
        http_client_factory=None,
    ) -> None:
        self._store = credential_store or get_credential_store()
        self._account = account if account is not None else os.environ.get("USER", "")
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )
        self._cached: dict | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_authorization_header(self) -> dict[str, str]:
        """Build the full header set for an outbound /v1/messages call.

        Returns the three headers every OAuth-authenticated Anthropic
        Messages call needs: ``Authorization`` (Bearer), ``anthropic-version``,
        ``anthropic-beta``. The beta header is required — the spike
        proved its absence causes scope rejection.

        Handles caching, proactive refresh, and the credential-missing
        hard-fail path.
        """
        # Fast path: cache hit and not expired
        if self._cached is not None and not self._is_expired(self._cached):
            return self._build_headers(self._cached)

        # Slow path: read + maybe refresh, under lock
        async with self._lock:
            # Double-check inside the lock — another coroutine may have
            # refreshed while we were waiting.
            if self._cached is None:
                self._cached = self._read_from_store()
            if self._is_expired(self._cached):
                self._cached = await self._do_refresh(self._cached)

        return self._build_headers(self._cached)

    async def refresh(self) -> None:
        """Force-refresh the cached credential.

        Used by ``POST /backends/claude-backend-api/refresh`` in Phase 5
        and as the on-401 recovery path in the Anthropic backend.
        """
        async with self._lock:
            if self._cached is None:
                self._cached = self._read_from_store()
            self._cached = await self._do_refresh(self._cached)

    def invalidate_cache(self) -> None:
        """Drop the in-memory cache without touching the credential store.

        Used as the on-401 recovery path: the backend catches a 401 from
        /v1/messages, calls invalidate_cache(), then retries once. The
        next get_authorization_header() call re-reads from the store and
        refreshes if needed.
        """
        self._cached = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_from_store(self) -> dict:
        """Read the credential store and parse the JSON payload.

        Raises:
            CredentialNotFoundError: The credential store has no entry.
            AuthError: The entry exists but doesn't parse as expected.
        """
        raw = self._store.read(KEYCHAIN_SERVICE, self._account)
        if raw is None:
            raise CredentialNotFoundError(
                "No Claude Code OAuth token found. Run 'claude auth login' to authenticate."
            )

        try:
            outer = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuthError(
                f"Claude Code credential store entry is not valid JSON: {exc}. "
                "Try running 'claude auth login' again."
            ) from exc

        if not isinstance(outer, dict) or "claudeAiOauth" not in outer:
            raise AuthError(
                "Claude Code credential store entry is missing the "
                "'claudeAiOauth' key. Try running 'claude auth login' again."
            )

        creds = outer["claudeAiOauth"]
        required = {"accessToken", "refreshToken", "expiresAt"}
        missing = required - set(creds.keys())
        if missing:
            raise AuthError(
                f"Claude Code credential store entry missing required keys: "
                f"{sorted(missing)}. Try running 'claude auth login' again."
            )
        return creds

    def _is_expired(self, creds: dict) -> bool:
        """Return True if the token should be refreshed.

        Uses the 60-second proactive refresh window — we refresh when
        the token has less than REFRESH_WINDOW_SECONDS of validity
        remaining, not when it's already expired.

        The ``expiresAt`` field is a unix epoch in **milliseconds** (not
        seconds), per the spike-validated Claude Code format.
        """
        expires_at_ms = creds.get("expiresAt", 0)
        now_ms = time.time() * 1000
        return now_ms >= expires_at_ms - (REFRESH_WINDOW_SECONDS * 1000)

    def _build_headers(self, creds: dict) -> dict[str, str]:
        """Build the three required headers from a validated credential."""
        return {
            "Authorization": f"Bearer {creds['accessToken']}",
            "anthropic-version": ANTHROPIC_VERSION,
            "anthropic-beta": ANTHROPIC_BETA,
        }

    async def _do_refresh(self, creds: dict) -> dict:
        """POST to the refresh endpoint and write back on success.

        Must be called while holding self._lock.

        Raises:
            AuthError: Refresh failed (401, network, 5xx after retries).
        """
        body = {
            "grant_type": "refresh_token",
            "refresh_token": creds["refreshToken"],
            "client_id": OAUTH_CLIENT_ID,
        }
        headers = {"content-type": "application/json"}

        try:
            async with self._http_factory() as client:
                resp = await client.post(OAUTH_REFRESH_URL, json=body, headers=headers)
        except httpx.RequestError as exc:
            raise AuthError(f"Refresh endpoint unreachable: {exc}. Try again in a moment.") from exc

        if resp.status_code == 401:
            raise AuthError(
                "Claude Code OAuth token expired and could not be refreshed. "
                "Run 'claude auth login' to re-authenticate."
            )

        if resp.status_code != 200:
            raise AuthError(
                f"OAuth refresh failed with status {resp.status_code}: "
                f"{resp.text[:500]}. Run 'claude auth login' to re-authenticate."
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AuthError(f"OAuth refresh response is not valid JSON: {exc}") from exc

        new_creds = self._convert_refresh_response(data, old_creds=creds)
        self._write_to_store(new_creds)
        logger.info(
            "claude-backend-api: OAuth token refreshed, new expiry in %.0fs",
            (new_creds["expiresAt"] - time.time() * 1000) / 1000,
        )
        return new_creds

    def _convert_refresh_response(self, data: dict, *, old_creds: dict) -> dict:
        """Convert the OAuth 2.0 refresh response to keychain shape.

        The refresh endpoint returns standard OAuth 2.0 fields:
          - access_token (string)
          - refresh_token (string, may be rotated)
          - expires_in (SECONDS)
          - token_type ("Bearer")
          - scope (space-separated string)

        The keychain stores:
          - accessToken (string)
          - refreshToken (string)
          - expiresAt (MILLISECONDS since epoch)
          - scopes (list of strings)
          - subscriptionType, rateLimitTier (preserved from old creds)
        """
        if "access_token" not in data:
            raise AuthError("OAuth refresh response missing 'access_token' field")
        if "refresh_token" not in data:
            raise AuthError("OAuth refresh response missing 'refresh_token' field")
        if "expires_in" not in data:
            raise AuthError("OAuth refresh response missing 'expires_in' field")

        # Convert seconds → milliseconds relative to now
        expires_at_ms = int((time.time() + int(data["expires_in"])) * 1000)

        # scope is a space-separated string; scopes is a list
        scope_str = data.get("scope", "")
        scopes = scope_str.split() if scope_str else old_creds.get("scopes", [])

        return {
            "accessToken": data["access_token"],
            "refreshToken": data["refresh_token"],
            "expiresAt": expires_at_ms,
            "scopes": scopes,
            # Preserve metadata the refresh response doesn't include
            "subscriptionType": old_creds.get("subscriptionType", "max"),
            "rateLimitTier": old_creds.get("rateLimitTier", "default_claude_max_5x"),
        }

    def _write_to_store(self, creds: dict) -> None:
        """Write the updated credential back to the platform store.

        Preserves the outer wrapper shape the CLI expects.
        """
        value = json.dumps({"claudeAiOauth": creds})
        self._store.write(KEYCHAIN_SERVICE, self._account, value)
