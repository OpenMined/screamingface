"""Codex CLI OAuth auth strategy -- reads tokens from ~/.codex/auth.json.

The Codex CLI stores its OAuth credentials as a plain JSON file on disk
(unlike Claude Code which uses the OS keychain). The file is written by
``codex auth login`` and contains:

.. code-block:: json

    {
        "OPENAI_API_KEY": null,
        "tokens": {
            "id_token": "<jwt>",
            "access_token": "<jwt>",
            "refresh_token": "<rt_...>",
            "account_id": "<uuid>"
        },
        "last_refresh": "<iso-timestamp>"
    }

The access token is a RS256-signed JWT with an ``exp`` claim (unix epoch
in seconds). We decode the JWT payload to check expiry -- no ``pyjwt``
dependency needed, just base64.

Refresh flow:
  POST https://auth.openai.com/oauth/token
  Body: {grant_type: "refresh_token", refresh_token, client_id}

Concurrency: same asyncio.Lock + double-checked locking pattern as
ClaudeCodeOAuth.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import tempfile
import time
from pathlib import Path

import httpx

from screamingface.plugins.llm_base.auth_base import AuthStrategy
from screamingface.plugins.llm_base.errors import AuthError, CredentialNotFoundError

logger = logging.getLogger(__name__)

AUTH_FILE_PATH = Path.home() / ".codex" / "auth.json"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

# RFC 8693 token exchange constants -- the Codex CLI's id_token has
# ChatGPT scopes only. To call the API we must exchange it for an
# API-capable access token via the token exchange grant type.
TOKEN_EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
TOKEN_EXCHANGE_SUBJECT_TYPE = "urn:ietf:params:oauth:token-type:id_token"
TOKEN_EXCHANGE_AUDIENCE = "https://api.openai.com/v1"

# Proactive refresh window -- refresh when the token has less than this
# many seconds of validity remaining.
REFRESH_WINDOW_SECONDS = 60


def _decode_jwt_exp(token: str) -> float | None:
    """Extract the ``exp`` claim from a JWT without signature verification.

    Returns the expiry as a unix epoch in seconds, or None if decoding
    fails. We only need the expiry timestamp, not verification.
    """
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    # Add padding if missing (base64url requires length % 4 == 0)
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload["exp"])
    except (json.JSONDecodeError, KeyError, ValueError, Exception):
        return None


class CodexOAuth(AuthStrategy):
    """Reads Codex CLI's OAuth token from ~/.codex/auth.json.

    Args:
        auth_file: Path to the credential file. Defaults to
            ``~/.codex/auth.json``. Tests inject a temp path.
        http_client_factory: Callable returning a new ``httpx.AsyncClient``.
            Tests inject a factory that returns a mocked client.
    """

    def __init__(
        self,
        *,
        auth_file: Path | None = None,
        http_client_factory=None,
    ) -> None:
        self._auth_file = auth_file or AUTH_FILE_PATH
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )
        self._cached: dict | None = None  # raw tokens from auth.json
        self._api_token: str | None = None  # exchanged API-capable token
        self._api_token_exp: float = 0  # expiry of the API token
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_authorization_header(self) -> dict[str, str]:
        """Build headers for an outbound OpenAI API call.

        Returns ``{"Authorization": "Bearer <access_token>"}``.

        The Codex CLI's OAuth tokens have ChatGPT scopes. For direct API
        access, the user should set ``OPENAI_API_KEY`` (checked first)
        or have a Codex Pro plan whose tokens carry API scopes.
        """
        # Check for explicit API key first (most reliable path)
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}

        # OAuth path: use the access_token from ~/.codex/auth.json
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
        """Drop the in-memory cache without touching the file on disk."""
        self._cached = None
        self._api_token = None
        self._api_token_exp = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_from_file(self) -> dict:
        """Read and parse ~/.codex/auth.json.

        Raises:
            CredentialNotFoundError: File does not exist.
            AuthError: File exists but doesn't parse as expected.
        """
        if not self._auth_file.exists():
            raise CredentialNotFoundError(
                "No Codex OAuth token found. Run 'codex auth login' to authenticate."
            )

        try:
            raw = self._auth_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthError(
                f"Codex credential file is not readable or not valid JSON: {exc}. "
                "Try running 'codex auth login' again."
            ) from exc

        if not isinstance(data, dict) or "tokens" not in data:
            raise AuthError(
                "Codex credential file is missing the 'tokens' key. "
                "Try running 'codex auth login' again."
            )

        tokens = data["tokens"]
        if not isinstance(tokens, dict):
            raise AuthError(
                "Codex credential file 'tokens' is not a dict. "
                "Try running 'codex auth login' again."
            )

        required = {"access_token", "refresh_token"}
        missing = required - set(tokens.keys())
        if missing:
            raise AuthError(
                f"Codex credential file missing required keys: "
                f"{sorted(missing)}. Try running 'codex auth login' again."
            )

        return tokens

    def _is_expired(self, tokens: dict) -> bool:
        """Return True if the access token should be refreshed.

        Decodes the JWT ``exp`` claim from the access token. Refreshes
        when the token has less than REFRESH_WINDOW_SECONDS remaining.
        """
        access_token = tokens.get("access_token", "")
        exp = _decode_jwt_exp(access_token)
        if exp is None:
            return True
        return time.time() >= exp - REFRESH_WINDOW_SECONDS

    def _is_id_token_expired(self, tokens: dict) -> bool:
        """Return True if the id_token is expired or missing.

        The id_token is needed for token exchange and may expire before
        the access_token.
        """
        id_token = tokens.get("id_token", "")
        if not id_token:
            return True
        exp = _decode_jwt_exp(id_token)
        if exp is None:
            return True
        return time.time() >= exp - REFRESH_WINDOW_SECONDS

    def _build_headers(self, tokens: dict) -> dict[str, str]:
        """Build the authorization header from validated tokens."""
        return {
            "Authorization": f"Bearer {tokens['access_token']}",
        }

    async def _do_refresh(self, tokens: dict) -> dict:
        """POST to the refresh endpoint and write back on success.

        Must be called while holding self._lock.

        Raises:
            AuthError: Refresh failed.
        """
        body = {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": OAUTH_CLIENT_ID,
        }
        headers = {"content-type": "application/json"}

        try:
            async with self._http_factory() as client:
                resp = await client.post(OAUTH_TOKEN_URL, json=body, headers=headers)
        except httpx.RequestError as exc:
            raise AuthError(
                f"OpenAI refresh endpoint unreachable: {exc}. Try again in a moment."
            ) from exc

        if resp.status_code == 401:
            raise AuthError(
                "Codex OAuth token expired and could not be refreshed. "
                "Run 'codex auth login' to re-authenticate."
            )

        if resp.status_code != 200:
            raise AuthError(
                f"OAuth refresh failed with status {resp.status_code}: "
                f"{resp.text[:500]}. Run 'codex auth login' to re-authenticate."
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AuthError(f"OAuth refresh response is not valid JSON: {exc}") from exc

        if "access_token" not in data:
            raise AuthError("OAuth refresh response missing 'access_token' field")
        if "refresh_token" not in data:
            raise AuthError("OAuth refresh response missing 'refresh_token' field")

        new_tokens = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            # Use fresh id_token from refresh if provided, else keep old
            "id_token": data.get("id_token") or tokens.get("id_token"),
            "account_id": tokens.get("account_id"),
        }

        self._write_to_file(new_tokens)
        exp = _decode_jwt_exp(data["access_token"])
        if exp:
            logger.info(
                "codex-backend-api: OAuth token refreshed, new expiry in %.0fs",
                exp - time.time(),
            )
        return new_tokens

    async def _do_token_exchange(self, tokens: dict) -> tuple[str, float]:
        """Exchange the id_token for an API-capable access token.

        The Codex CLI's OAuth tokens have ChatGPT scopes only (openid,
        profile, email, offline_access). To call the OpenAI API we must
        perform an RFC 8693 token exchange: swap the id_token for a
        token with API scopes (model.request, etc.).

        Must be called while holding self._lock.

        Returns:
            (api_access_token, expiry_timestamp)

        Raises:
            AuthError: Exchange failed.
        """
        id_token = tokens.get("id_token")
        if not id_token:
            raise AuthError(
                "Codex credential file missing 'id_token' required for "
                "token exchange. Run 'codex auth login' again."
            )

        # RFC 8693 token exchange uses form-encoded body, not JSON
        body = {
            "grant_type": TOKEN_EXCHANGE_GRANT_TYPE,
            "subject_token": id_token,
            "subject_token_type": TOKEN_EXCHANGE_SUBJECT_TYPE,
            "audience": TOKEN_EXCHANGE_AUDIENCE,
            "client_id": OAUTH_CLIENT_ID,
        }
        headers = {"content-type": "application/x-www-form-urlencoded"}

        try:
            async with self._http_factory() as client:
                resp = await client.post(OAUTH_TOKEN_URL, data=body, headers=headers)
        except httpx.RequestError as exc:
            raise AuthError(
                f"Token exchange endpoint unreachable: {exc}. Try again in a moment."
            ) from exc

        if resp.status_code != 200:
            raise AuthError(
                f"Token exchange failed with status {resp.status_code}: "
                f"{resp.text[:500]}. Run 'codex auth login' to re-authenticate."
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AuthError(f"Token exchange response is not valid JSON: {exc}") from exc

        api_token = data.get("access_token")
        if not api_token:
            raise AuthError("Token exchange response missing 'access_token' field")

        # Determine expiry from the new token
        exp = _decode_jwt_exp(api_token)
        if exp is None:
            # If we can't decode exp, use expires_in from response
            expires_in = data.get("expires_in", 3600)
            exp = time.time() + float(expires_in)

        logger.info(
            "codex-backend-api: token exchange complete, API token expires in %.0fs",
            exp - time.time(),
        )
        return api_token, exp

    def _write_to_file(self, tokens: dict) -> None:
        """Write updated tokens back to the credential file atomically.

        Uses write-to-temp-then-rename for crash safety.
        """
        data: dict = {}
        # Preserve existing file structure (OPENAI_API_KEY, etc.)
        if self._auth_file.exists():
            try:
                data = json.loads(self._auth_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}

        data["tokens"] = tokens
        data["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        parent = self._auth_file.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self._auth_file)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
