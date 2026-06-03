"""Gemini CLI auth strategy — reads OAuth credentials from ``~/.gemini/oauth_creds.json``.

Hybrid strategy: if ``GOOGLE_API_KEY`` or ``GEMINI_API_KEY`` is set the
call short-circuits to an ``x-goog-api-key`` header. Otherwise the
shared :class:`~screamingface.plugins.llm_base.oauth_base.OAuthStrategy`
flow handles caching, locking, and the proactive refresh.

Google-specific details this file owns:

- Credential path: ``~/.gemini/oauth_creds.json`` (plain JSON file,
  like Codex; unlike Claude Code's keychain).
- Refresh endpoint: ``https://oauth2.googleapis.com/token`` with a
  form-encoded body and a ``client_secret`` (Google requires it; the
  CLI's public value is embedded).
- ``expiry_date`` is in **milliseconds** (like Claude, unlike Codex).
- Refresh response does NOT rotate ``refresh_token`` — the old one is
  preserved.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import tempfile
import time
from pathlib import Path

import httpx

from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
from screamingface.plugins.llm_base.errors import AuthError, CredentialNotFoundError
from screamingface.plugins.llm_base.oauth_base import OAuthStrategy

logger = logging.getLogger(__name__)

OAUTH_CREDS_PATH = Path.home() / ".gemini" / "oauth_creds.json"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Public OAuth client credentials from the gemini-cli source.
OAUTH_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
OAUTH_CLIENT_SECRET = "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"

# Retained at module scope for test imports / external callers.
REFRESH_WINDOW_SECONDS = 60

CLI_VERSION = "0.37.1"


class GeminiAuth(OAuthStrategy):
    """Hybrid Gemini auth: API-key env var OR OAuth file.

    Args:
        creds_file: Path to the credential file. Tests inject a temp path.
        http_client_factory: Callable returning a new ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        *,
        creds_file: Path | None = None,
        http_client_factory=None,
        aigw_source: AigwTokenSource | None = None,
    ) -> None:
        super().__init__(aigw_source=aigw_source)
        self._creds_file = creds_file or OAUTH_CREDS_PATH
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )

    def is_api_key_auth(self) -> bool:
        """True when the strategy is short-circuiting to API-key headers."""
        return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))

    # ------------------------------------------------------------------
    # OAuthStrategy hooks
    # ------------------------------------------------------------------

    def _header_override(self) -> dict[str, str] | None:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if api_key:
            return {"x-goog-api-key": api_key}
        return None

    def _read_credential(self) -> dict:
        if not self._creds_file.exists():
            raise CredentialNotFoundError(
                "No Gemini OAuth token found. Run 'gemini auth login' to authenticate."
            )
        try:
            data = json.loads(self._creds_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthError(
                f"Gemini credential file is not readable or not valid JSON: {exc}. "
                "Try running 'gemini auth login' again."
            ) from exc
        if not isinstance(data, dict):
            raise AuthError("Gemini credential file is not a JSON object.")
        missing = {"access_token", "refresh_token"} - set(data.keys())
        if missing:
            raise AuthError(
                f"Gemini credential file missing required keys: {sorted(missing)}. "
                "Try running 'gemini auth login' again."
            )
        return data

    def _aigw_creds_shape(self, access_token: str, expires_at) -> dict:
        """Build a Gemini-shaped creds dict from an aigw-supplied token.

        Gemini's _build_headers reads access_token. The refresh_token /
        expiry_date fields aren't used on the aigw path because aigw owns refresh.
        """
        return {
            "access_token": access_token,
            "refresh_token": "",
            "expiry_date": int(expires_at.timestamp() * 1000),
            "token_type": "Bearer",
        }

    def _is_expired(self, creds: dict) -> bool:
        """``expiry_date`` is unix epoch in **milliseconds**."""
        if self._aigw_source is not None:
            # OAuthStrategy bypasses its outer cache on the aigw path; this is
            # retained as a guard for tests and direct private-hook callers.
            return False
        # existing logic
        expiry_ms = creds.get("expiry_date", 0)
        now_ms = time.time() * 1000
        return now_ms >= expiry_ms - (self.refresh_window_seconds * 1000)

    def _build_headers(self, creds: dict) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {creds['access_token']}",
            "User-Agent": (
                f"GeminiCLI/{CLI_VERSION}/gemini-2.5-flash"
                f" ({platform.system().lower()}; {platform.machine()}; terminal)"
            ),
        }

    async def _refresh_credential(self, creds: dict) -> dict:
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

        # Google does NOT rotate refresh_token — preserve the old one.
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

    # Backward-compat alias — legacy tests still call ``_read_from_file``.
    _read_from_file = _read_credential

    def _write_to_file(self, creds: dict) -> None:
        """Atomic write-then-rename."""
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
