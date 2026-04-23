"""Gemini CLI auth strategy — reads OAuth credentials from ~/.gemini/oauth_creds.json.

The Gemini CLI stores its OAuth credentials as a plain JSON file:

.. code-block:: json

    {
        "access_token": "ya29.a0...",
        "scope": "https://www.googleapis.com/auth/...",
        "token_type": "Bearer",
        "id_token": "eyJ...",
        "expiry_date": 1776081543971,
        "refresh_token": "1//03j6L1..."
    }

``expiry_date`` is in **milliseconds** since epoch (like Claude Code's
``expiresAt``).

Refresh flow:
  POST https://oauth2.googleapis.com/token
  Body (form-encoded): {
      grant_type: "refresh_token",
      refresh_token,
      client_id,
      client_secret   ← Google requires both (unlike Anthropic/OpenAI)
  }

Google does NOT rotate the refresh_token — the old one stays valid.
The refresh response returns a new access_token + expires_in (seconds)
but NOT a new refresh_token, so we preserve the original.

Auth routing:
  - API key (GOOGLE_API_KEY / GEMINI_API_KEY) → generativelanguage.googleapis.com
  - OAuth token → cloudcode-pa.googleapis.com/v1internal (Code Assist API)

Concurrency: same asyncio.Lock + double-checked locking pattern as
ClaudeCodeOAuth.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import tempfile
import time
from pathlib import Path

import httpx

from screamingface.plugins.llm_base.auth_base import AuthStrategy
from screamingface.plugins.llm_base.errors import AuthError, CredentialNotFoundError

logger = logging.getLogger(__name__)

OAUTH_CREDS_PATH = Path.home() / ".gemini" / "oauth_creds.json"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Public OAuth client credentials from the gemini-cli source
OAUTH_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
OAUTH_CLIENT_SECRET = "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"

REFRESH_WINDOW_SECONDS = 60

CLI_VERSION = "0.37.1"


class GeminiAuth(AuthStrategy):
    """Reads Gemini CLI's OAuth token from ~/.gemini/oauth_creds.json.

    Priority:
    1. GOOGLE_API_KEY or GEMINI_API_KEY env var (x-goog-api-key header)
    2. OAuth Bearer token from ~/.gemini/oauth_creds.json

    Args:
        creds_file: Path to the credential file. Tests inject a temp path.
        http_client_factory: Callable returning a new ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        *,
        creds_file: Path | None = None,
        http_client_factory=None,
    ) -> None:
        self._creds_file = creds_file or OAUTH_CREDS_PATH
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )
        self._cached: dict | None = None
        self._lock = asyncio.Lock()

    def is_api_key_auth(self) -> bool:
        """Return True if using an explicit API key (not OAuth)."""
        return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))

    async def get_authorization_header(self) -> dict[str, str]:
        """Build headers for an outbound Gemini API call.

        Returns ``{"Authorization": "Bearer <access_token>"}`` for OAuth,
        or ``{"x-goog-api-key": "<key>"}`` for API key auth.
        """
        # Check for explicit API key first
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if api_key:
            return {"x-goog-api-key": api_key}

        # OAuth path
        if self._cached is not None and not self._is_expired(self._cached):
            return self._build_headers(self._cached)

        async with self._lock:
            if self._cached is None:
                self._cached = self._read_from_file()
            if self._is_expired(self._cached):
                self._cached = await self._do_refresh(self._cached)

        return self._build_headers(self._cached)

    async def refresh(self) -> None:
        """Force-refresh the cached credential."""
        async with self._lock:
            if self._cached is None:
                self._cached = self._read_from_file()
            self._cached = await self._do_refresh(self._cached)

    def invalidate_cache(self) -> None:
        """Drop the in-memory cache."""
        self._cached = None

    def _read_from_file(self) -> dict:
        """Read and parse ~/.gemini/oauth_creds.json."""
        if not self._creds_file.exists():
            raise CredentialNotFoundError(
                "No Gemini OAuth token found. Run 'gemini auth login' to authenticate."
            )
        try:
            raw = self._creds_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthError(
                f"Gemini credential file is not readable or not valid JSON: {exc}. "
                "Try running 'gemini auth login' again."
            ) from exc

        if not isinstance(data, dict):
            raise AuthError("Gemini credential file is not a JSON object.")

        required = {"access_token", "refresh_token"}
        missing = required - set(data.keys())
        if missing:
            raise AuthError(
                f"Gemini credential file missing required keys: {sorted(missing)}. "
                "Try running 'gemini auth login' again."
            )
        return data

    def _is_expired(self, creds: dict) -> bool:
        """Return True if the access token should be refreshed.

        ``expiry_date`` is in milliseconds since epoch.
        """
        expiry_ms = creds.get("expiry_date", 0)
        now_ms = time.time() * 1000
        return now_ms >= expiry_ms - (REFRESH_WINDOW_SECONDS * 1000)

    def _build_headers(self, creds: dict) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {creds['access_token']}",
            "User-Agent": (
                f"GeminiCLI/{CLI_VERSION}/gemini-2.5-flash"
                f" ({platform.system().lower()}; {platform.machine()}; terminal)"
            ),
        }

    async def _do_refresh(self, creds: dict) -> dict:
        """POST to Google's token endpoint to refresh the access token.

        Google requires client_secret in the refresh body (unlike
        Anthropic/OpenAI). Google does NOT rotate the refresh_token.
        """
        # Google token endpoint uses form-encoded body, not JSON
        body = {
            "grant_type": "refresh_token",
            "refresh_token": creds["refresh_token"],
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
        }

        try:
            async with self._http_factory() as client:
                resp = await client.post(
                    GOOGLE_TOKEN_URL,
                    data=body,
                    headers={"content-type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as exc:
            raise AuthError(
                f"Google token endpoint unreachable: {exc}. Try again in a moment."
            ) from exc

        if resp.status_code != 200:
            raise AuthError(
                f"Google OAuth refresh failed with status {resp.status_code}: "
                f"{resp.text[:500]}. Run 'gemini auth login' to re-authenticate."
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AuthError(f"Google OAuth refresh response is not valid JSON: {exc}") from exc

        if "access_token" not in data:
            raise AuthError("Google OAuth refresh response missing 'access_token'")

        # Google does NOT return a new refresh_token — preserve the old one
        expires_in = data.get("expires_in", 3600)
        expiry_ms = int((time.time() + float(expires_in)) * 1000)

        new_creds = {
            **creds,
            "access_token": data["access_token"],
            "expiry_date": expiry_ms,
        }
        if "id_token" in data:
            new_creds["id_token"] = data["id_token"]

        self._write_to_file(new_creds)
        logger.info(
            "gemini-backend-api: OAuth token refreshed, new expiry in %.0fs",
            float(expires_in),
        )
        return new_creds

    def _write_to_file(self, creds: dict) -> None:
        """Write updated credentials back to the file atomically."""
        parent = self._creds_file.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(creds, f, indent=2)
            os.replace(tmp_path, self._creds_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
