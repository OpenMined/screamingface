"""Claude Code OAuth auth strategy — reads the token from the credential store.

Every detail here was validated by the SF-77 spike
(``apps/server/scripts/oauth_spike.py``,
``apps/server/docs/oauth-spike-findings.md``). Do not change without
re-running the spike or at least understanding the spike's findings.

The flow — caching, double-checked locking, proactive refresh — lives
in :class:`~screamingface.plugins.llm_base.oauth_base.OAuthStrategy`.
This module just implements the four provider-specific hooks:

1. ``_read_credential`` — read the JSON blob Claude Code writes under
   ``"Claude Code-credentials"`` in the platform credential store.
2. ``_is_expired`` — compare ``expiresAt`` (unix epoch in milliseconds)
   against the 60-second proactive refresh window.
3. ``_refresh_credential`` — POST to
   ``https://platform.claude.com/v1/oauth/token`` with
   ``{grant_type: "refresh_token", refresh_token, client_id, scope}`` and
   convert the OAuth 2.0 response shape (snake_case, ``expires_in``
   seconds) back to the keychain shape (camelCase, ``expiresAt`` ms).
4. ``_build_headers`` — the three required Anthropic headers:
   ``Authorization: Bearer``, ``anthropic-version``, ``anthropic-beta``.
   The beta header is REQUIRED — the spike proved its absence causes
   scope rejection.

Concurrency note lives on the base class — a per-instance
``asyncio.Lock`` with double-checked locking.
"""

from __future__ import annotations

import json
import logging
import os
import time

import httpx

from screamingface.plugins.llm_base.credential_store import (
    CredentialStore,
    get_credential_store,
)
from screamingface.plugins.llm_base.errors import AuthError, CredentialNotFoundError
from screamingface.plugins.llm_base.oauth_base import OAuthStrategy

logger = logging.getLogger(__name__)

# Constants validated against Claude Code 2.1.142.
KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_REFRESH_URL = "https://platform.claude.com/v1/oauth/token"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # public Claude Code OAuth app
OAUTH_REFRESH_SCOPES = [
    "user:profile",
    "user:inference",
    "user:sessions:claude_code",
    "user:mcp_servers",
    "user:file_upload",
]
ANTHROPIC_VERSION = "2023-06-01"
# Beta features: ``oauth-2025-04-20`` is required for OAuth bearer tokens,
# ``claude-code-*`` gives access to the Claude Code rate-limit pool.
ANTHROPIC_BETA = ",".join(
    [
        "claude-code-20250219",
        "oauth-2025-04-20",
        "interleaved-thinking-2025-05-14",
        "prompt-caching-scope-2026-01-05",
    ]
)

# Retained at module level so existing tests and callers keep working.
# The value lives on :class:`OAuthStrategy.refresh_window_seconds`; we
# just re-export it here.
REFRESH_WINDOW_SECONDS = 60


class ClaudeCodeOAuth(OAuthStrategy):
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
        super().__init__()
        self._store = credential_store or get_credential_store()
        self._account = account if account is not None else os.environ.get("USER", "")
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )

    # ------------------------------------------------------------------
    # OAuthStrategy hooks
    # ------------------------------------------------------------------

    def _read_credential(self) -> dict:
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
        missing = {"accessToken", "refreshToken", "expiresAt"} - set(creds.keys())
        if missing:
            raise AuthError(
                f"Claude Code credential store entry missing required keys: "
                f"{sorted(missing)}. Try running 'claude auth login' again."
            )
        return creds

    def _is_expired(self, creds: dict) -> bool:
        """expiresAt is unix epoch in **milliseconds** — spike-validated."""
        expires_at_ms = creds.get("expiresAt", 0)
        now_ms = time.time() * 1000
        return now_ms >= expires_at_ms - (self.refresh_window_seconds * 1000)

    def _build_headers(self, creds: dict) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {creds['accessToken']}",
            "anthropic-version": ANTHROPIC_VERSION,
            "anthropic-beta": ANTHROPIC_BETA,
        }

    async def _refresh_credential(self, creds: dict) -> dict:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": creds["refreshToken"],
            "client_id": OAUTH_CLIENT_ID,
            "scope": " ".join(OAUTH_REFRESH_SCOPES),
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

    # ------------------------------------------------------------------
    # Keychain-shape plumbing
    # ------------------------------------------------------------------

    def _convert_refresh_response(self, data: dict, *, old_creds: dict) -> dict:
        """Convert the OAuth 2.0 refresh response to Claude Code keychain shape.

        Refresh endpoint returns standard OAuth 2.0 fields (snake_case,
        ``expires_in`` seconds); the keychain stores camelCase with
        ``expiresAt`` in milliseconds. ``subscriptionType``/``rateLimitTier``
        are preserved from the old credential since the refresh response
        doesn't include them.
        """
        for required_field in ("access_token", "refresh_token", "expires_in"):
            if required_field not in data:
                raise AuthError(f"OAuth refresh response missing '{required_field}' field")

        expires_at_ms = int((time.time() + int(data["expires_in"])) * 1000)
        scope_str = data.get("scope", "")
        scopes = scope_str.split() if scope_str else old_creds.get("scopes", [])

        return {
            "accessToken": data["access_token"],
            "refreshToken": data["refresh_token"],
            "expiresAt": expires_at_ms,
            "scopes": scopes,
            "subscriptionType": old_creds.get("subscriptionType", "max"),
            "rateLimitTier": old_creds.get("rateLimitTier", "default_claude_max_5x"),
        }

    def _write_to_store(self, creds: dict) -> None:
        """Write the updated credential back, preserving the CLI's wrapper."""
        value = json.dumps({"claudeAiOauth": creds})
        self._store.write(KEYCHAIN_SERVICE, self._account, value)
