"""Anthropic OAuth strategy — reads Claude Code's keychain entry, refreshes via console.anthropic.com.

Validated against the Claude Code CLI's behavior (see SF-77 spike notes
in apps/server/docs/oauth-spike-findings.md). Concretely:

- The keychain entry is JSON-wrapped under a top-level ``claudeAiOauth`` key.
- ``expiresAt`` is a unix-epoch value in **milliseconds**, not seconds.
- The refresh response is standard OAuth 2.0 (snake_case, ``expires_in``
  in seconds); we convert back to the keychain shape on write.
- Three headers are required on every Anthropic call: ``Authorization``,
  ``anthropic-version``, ``anthropic-beta``. The beta header is non-optional
  for OAuth bearer tokens.
"""

from __future__ import annotations

import json
import logging
import os
import time

import httpx

from aigateway.core.credential_store import CredentialStore, get_credential_store
from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.core.oauth_base import BaseOAuthStrategy

logger = logging.getLogger(__name__)

KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_REFRESH_URL = "https://console.anthropic.com/v1/oauth/token"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_BETA = ",".join(
    [
        "claude-code-20250219",
        "oauth-2025-04-20",
        "interleaved-thinking-2025-05-14",
        "prompt-caching-scope-2026-01-05",
    ]
)


class AnthropicOAuth(BaseOAuthStrategy):
    """Read Claude Code's OAuth token from the OS keychain; refresh automatically."""

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
                f"Claude Code keychain entry is not valid JSON: {exc}. "
                "Re-run 'claude auth login'."
            ) from exc

        if not isinstance(outer, dict) or "claudeAiOauth" not in outer:
            raise AuthError(
                "Claude Code keychain entry missing 'claudeAiOauth' key. Re-run 'claude auth login'."
            )

        creds = outer["claudeAiOauth"]
        missing = {"accessToken", "refreshToken", "expiresAt"} - set(creds.keys())
        if missing:
            raise AuthError(
                f"Claude Code keychain entry missing required keys: {sorted(missing)}. "
                "Re-run 'claude auth login'."
            )
        return creds

    def _is_expired(self, creds: dict) -> bool:
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
        }
        try:
            async with self._http_factory() as client:
                resp = await client.post(
                    OAUTH_REFRESH_URL, json=body, headers={"content-type": "application/json"}
                )
        except httpx.RequestError as exc:
            raise AuthError(f"Refresh endpoint unreachable: {exc}.") from exc

        if resp.status_code == 401:
            raise AuthError(
                "Anthropic OAuth refresh returned 401. Re-run 'claude auth login'."
            )
        if resp.status_code != 200:
            raise AuthError(
                f"OAuth refresh failed with status {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AuthError(f"OAuth refresh response not valid JSON: {exc}") from exc

        new_creds = self._convert_refresh_response(data, old_creds=creds)
        self._write_to_store(new_creds)
        logger.info(
            "anthropic: OAuth token refreshed; new expiry in %.0fs",
            (new_creds["expiresAt"] - time.time() * 1000) / 1000,
        )
        return new_creds

    def _convert_refresh_response(self, data: dict, *, old_creds: dict) -> dict:
        for required in ("access_token", "refresh_token", "expires_in"):
            if required not in data:
                raise AuthError(f"OAuth refresh response missing '{required}' field")
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
        value = json.dumps({"claudeAiOauth": creds})
        self._store.write(KEYCHAIN_SERVICE, self._account, value)
