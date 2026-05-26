"""Codex CLI OAuth auth strategy — reads tokens from ``~/.codex/auth.json``.

The shared caching + locking + refresh flow lives in
:class:`~screamingface.plugins.llm_base.oauth_base.OAuthStrategy`.
This module supplies the Codex-specific pieces:

1. ``_read_credential`` — load ``~/.codex/auth.json`` and extract the
   ``tokens`` sub-dict.
2. ``_is_expired`` — decode the JWT ``exp`` claim (unix epoch in
   *seconds*) and compare against the 60-second proactive refresh
   window.
3. ``_refresh_credential`` — POST to ``https://auth.openai.com/oauth/token``
   with ``{grant_type: "refresh_token", refresh_token, client_id}``
   and write back atomically.
4. ``_build_headers`` — ``{"Authorization": "Bearer <access_token>"}``.

``_header_override`` returns an explicit ``OPENAI_API_KEY`` as a Bearer
header when set, bypassing the OAuth flow entirely.

Codex's JWT tokens carry ChatGPT scopes; the backend uses
``chatgpt.com/backend-api/codex/responses`` directly. The RFC 8693
token-exchange path to swap for an ``api.openai.com``-scoped token
(see :meth:`CodexOAuth._do_token_exchange`) is retained for future use
but not on the default path.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
import time
from pathlib import Path

import httpx

from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
from screamingface.plugins.llm_base.errors import AuthError, CredentialNotFoundError
from screamingface.plugins.llm_base.oauth_base import OAuthStrategy

logger = logging.getLogger(__name__)

AUTH_FILE_PATH = Path.home() / ".codex" / "auth.json"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

# RFC 8693 token exchange — the Codex CLI's id_token has ChatGPT scopes
# only. Exchanging for an API-capable token is preserved as a subclass
# method for future use; the default path uses the raw ChatGPT token
# against chatgpt.com/backend-api/codex/responses.
TOKEN_EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
TOKEN_EXCHANGE_SUBJECT_TYPE = "urn:ietf:params:oauth:token-type:id_token"

# Retained at module scope for test imports / external callers. The
# effective value lives on :attr:`OAuthStrategy.refresh_window_seconds`.
REFRESH_WINDOW_SECONDS = 60


def _decode_jwt_exp(token: str) -> float | None:
    """Return the unsigned JWT ``exp`` claim (seconds since epoch), or None."""
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload["exp"])
    except Exception:
        return None


class CodexOAuth(OAuthStrategy):
    """Reads Codex CLI's OAuth token from ``~/.codex/auth.json``.

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
        aigw_source: AigwTokenSource | None = None,
    ) -> None:
        super().__init__(aigw_source=aigw_source)
        self._auth_file = auth_file or AUTH_FILE_PATH
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )
        # API-token exchange state (RFC 8693 path, optional)
        self._api_token: str | None = None
        self._api_token_exp: float = 0

    # ------------------------------------------------------------------
    # OAuthStrategy hooks
    # ------------------------------------------------------------------

    def _header_override(self) -> dict[str, str] | None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}
        return None

    def _read_credential(self) -> dict:
        if not self._auth_file.exists():
            raise CredentialNotFoundError(
                "No Codex OAuth token found. Run 'codex auth login' to authenticate."
            )
        try:
            data = json.loads(self._auth_file.read_text(encoding="utf-8"))
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
        missing = {"access_token", "refresh_token"} - set(tokens.keys())
        if missing:
            raise AuthError(
                f"Codex credential file missing required keys: "
                f"{sorted(missing)}. Try running 'codex auth login' again."
            )
        return tokens

    def _is_expired(self, creds: dict) -> bool:
        # On the aigw path the token is managed externally; never trigger a
        # local refresh (AigwTokenSource owns cache + refresh internally).
        if self._aigw_source is not None:
            return False
        exp = _decode_jwt_exp(creds.get("access_token", ""))
        if exp is None:
            return True
        return time.time() >= exp - self.refresh_window_seconds

    def _build_headers(self, creds: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {creds['access_token']}"}

    def _aigw_creds_shape(self, access_token: str, expires_at) -> dict:
        """Build a Codex-shaped creds dict from an aigw-supplied token.

        Codex's _build_headers only reads access_token. The refresh_token /
        id_token fields aren't used on the aigw path because aigw owns refresh.
        """
        return {
            "access_token": access_token,
            "refresh_token": "",
            "id_token": "",
        }

    async def _refresh_credential(self, creds: dict) -> dict:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": creds["refresh_token"],
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
        for required_field in ("access_token", "refresh_token"):
            if required_field not in data:
                raise AuthError(f"OAuth refresh response missing '{required_field}' field")

        new_tokens = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "id_token": data.get("id_token") or creds.get("id_token"),
            "account_id": creds.get("account_id"),
        }
        self._write_to_file(new_tokens)

        exp = _decode_jwt_exp(data["access_token"])
        if exp:
            logger.info(
                "codex-backend-api: OAuth token refreshed, new expiry in %.0fs",
                exp - time.time(),
            )
        return new_tokens

    # ------------------------------------------------------------------
    # Codex-specific extras
    # ------------------------------------------------------------------

    def invalidate_cache(self) -> None:
        super().invalidate_cache()
        self._api_token = None
        self._api_token_exp = 0

    def get_account_id(self) -> str:
        """Return the ``chatgpt_account_id`` from the cached tokens."""
        if self._cached is None:
            self._cached = self._read_credential()
        return self._cached.get("account_id", "")

    # Backward-compat alias — legacy tests still call ``_read_from_file``.
    _read_from_file = _read_credential

    def _is_id_token_expired(self, tokens: dict) -> bool:
        """True if the id_token (used by the RFC 8693 exchange) is stale."""
        id_token = tokens.get("id_token", "")
        if not id_token:
            return True
        exp = _decode_jwt_exp(id_token)
        if exp is None:
            return True
        return time.time() >= exp - self.refresh_window_seconds

    async def _do_token_exchange(self, tokens: dict) -> tuple[str, float]:
        """RFC 8693: swap the id_token for an API-scoped access token.

        Preserved for future use against ``api.openai.com``; not on the
        default path (which uses the raw ChatGPT token against
        chatgpt.com).
        """
        id_token = tokens.get("id_token")
        if not id_token:
            raise AuthError(
                "Codex credential file missing 'id_token' required for "
                "token exchange. Run 'codex auth login' again."
            )

        body = {
            "grant_type": TOKEN_EXCHANGE_GRANT_TYPE,
            "client_id": OAUTH_CLIENT_ID,
            "requested_token": "openai-api-key",
            "subject_token": id_token,
            "subject_token_type": TOKEN_EXCHANGE_SUBJECT_TYPE,
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

        exp = _decode_jwt_exp(api_token)
        if exp is None:
            expires_in = data.get("expires_in", 3600)
            exp = time.time() + float(expires_in)

        logger.info(
            "codex-backend-api: token exchange complete, API token expires in %.0fs",
            exp - time.time(),
        )
        return api_token, exp

    def _write_to_file(self, tokens: dict) -> None:
        """Atomic write-then-rename, preserving any non-``tokens`` fields."""
        data: dict = {}
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
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
