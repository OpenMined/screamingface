from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import jwt

from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.core.oauth_base import BaseOAuthStrategy
from aigateway.core.oauth_identity import AccountIdentity

from .oauth_config import CODEX_OAUTH_CLIENT_ID, CODEX_OAUTH_SCOPE, CODEX_OAUTH_TOKEN_URL

logger = logging.getLogger(__name__)


def resolve_codex_auth_path() -> Path:
    codex_home = os.getenv("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "auth.json"
    return Path.home() / ".codex" / "auth.json"


def _decode_jwt_claims(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


def _decode_jwt_exp(token: str) -> float | None:
    try:
        return float(_decode_jwt_claims(token)["exp"])
    except Exception:
        return None


def _atomic_write_auth_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    original_mode = path.stat().st_mode & 0o777 if path.exists() else None
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle)
            handle.write("\n")
        os.replace(tmp_path, path)
        if original_mode is not None and original_mode & 0o777 < 0o600:
            try:
                os.chmod(path, original_mode)
            except OSError:
                logger.warning("failed to restore restrictive permissions on %s", path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _read_auth_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CredentialNotFoundError(
            "Codex auth file not found. Run `codex login` with file-backed storage "
            "or set CODEX_HOME to the directory containing auth.json."
        )
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise AuthError("Codex auth file is not valid JSON") from exc
    if not isinstance(data, dict):
        raise AuthError("Codex auth file must contain a JSON object")
    return data


class CodexOAuth(BaseOAuthStrategy):
    def __init__(
        self,
        profile_name: str,
        *,
        auth_file: Path | None = None,
        http_client_factory=None,
    ) -> None:
        super().__init__(profile_name=profile_name)
        self.auth_file = auth_file
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )

    def keychain_service(self) -> str:
        return f"aigateway:codex:{self.profile_name}"

    def keychain_account(self) -> str:
        return "file-backed"

    def _write_to_store(self, creds: dict) -> None:
        raise AuthError("Codex credentials are file-backed; gateway keychain writes are disabled")

    def _header_override(self) -> dict[str, str] | None:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}
        return None

    def _auth_path(self) -> Path:
        return self.auth_file or resolve_codex_auth_path()

    def _read_credential(self) -> dict:
        auth_path = self._auth_path()
        data = _read_auth_json(auth_path)
        api_key = data.get("OPENAI_API_KEY")
        if isinstance(api_key, str) and api_key:
            return {"kind": "api_key", "api_key": api_key}
        tokens = data.get("tokens")
        if not isinstance(tokens, dict):
            raise CredentialNotFoundError("Codex auth file has no file-backed OAuth tokens")
        for key in ("access_token", "refresh_token"):
            if not tokens.get(key):
                raise CredentialNotFoundError(f"Codex auth file missing token field {key!r}")
        return {"kind": "oauth", "auth_file": str(auth_path), **tokens}

    def _is_expired(self, creds: dict) -> bool:
        if creds.get("kind") == "api_key":
            return False
        access_token = creds.get("access_token")
        if not isinstance(access_token, str):
            return True
        exp = _decode_jwt_exp(access_token)
        if exp is None:
            return True
        return time.time() >= exp - self.refresh_window_seconds

    async def _refresh_credential(self, creds: dict) -> dict:
        if creds.get("kind") == "api_key":
            return creds
        refresh_token = creds.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            fallback = self._api_key_fallback()
            if fallback is not None:
                return fallback
            raise AuthError("Codex refresh token is missing; run `codex login` again")
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "scope": CODEX_OAUTH_SCOPE,
        }
        try:
            async with self._http_factory() as client:
                resp = await client.post(
                    CODEX_OAUTH_TOKEN_URL,
                    json=body,
                    headers={"content-type": "application/json"},
                )
        except httpx.RequestError as exc:
            fallback = self._api_key_fallback()
            if fallback is not None:
                return fallback
            raise AuthError(f"Codex refresh endpoint unreachable: {exc}") from exc
        if resp.status_code != 200:
            fallback = self._api_key_fallback()
            if fallback is not None:
                return fallback
            raise AuthError(f"Codex OAuth refresh failed status {resp.status_code}")
        try:
            refreshed: dict[str, Any] = resp.json()
        except json.JSONDecodeError as exc:
            raise AuthError("Codex OAuth refresh response was not JSON") from exc
        if not refreshed.get("access_token") or not refreshed.get("refresh_token"):
            raise AuthError("Codex OAuth refresh response missing required tokens")

        auth_path = Path(str(creds.get("auth_file") or self._auth_path()))
        data = _read_auth_json(auth_path)
        raw_old_tokens = data.get("tokens")
        old_tokens: dict[str, Any] = raw_old_tokens if isinstance(raw_old_tokens, dict) else {}
        tokens = {
            **old_tokens,
            "access_token": refreshed["access_token"],
            "refresh_token": refreshed["refresh_token"],
            "id_token": refreshed.get("id_token")
            or creds.get("id_token")
            or old_tokens.get("id_token"),
            "account_id": refreshed.get("account_id")
            or creds.get("account_id")
            or old_tokens.get("account_id"),
        }
        data["tokens"] = {k: v for k, v in tokens.items() if v is not None}
        data["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _atomic_write_auth_file(auth_path, data)
        return {"kind": "oauth", "auth_file": str(auth_path), **data["tokens"]}

    def _build_headers(self, creds: dict) -> dict[str, str]:
        if creds.get("kind") == "api_key":
            return {"Authorization": f"Bearer {creds['api_key']}"}
        headers = {"Authorization": f"Bearer {creds['access_token']}"}
        account_id = creds.get("account_id")
        if isinstance(account_id, str) and account_id:
            headers["ChatGPT-Account-Id"] = account_id
        return headers

    def extract_identity(self, token_response: dict) -> AccountIdentity | None:
        id_token = token_response.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            return None
        try:
            claims = _decode_jwt_claims(id_token)
        except Exception:
            return None
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            return None
        return AccountIdentity(
            sub=sub,
            email=claims.get("email") if isinstance(claims.get("email"), str) else None,
            name=claims.get("name") if isinstance(claims.get("name"), str) else None,
        )

    def _api_key_fallback(self) -> dict[str, str] | None:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return {"kind": "api_key", "api_key": api_key}
        try:
            data = _read_auth_json(self._auth_path())
        except Exception:
            return None
        file_api_key = data.get("OPENAI_API_KEY")
        if isinstance(file_api_key, str) and file_api_key:
            return {"kind": "api_key", "api_key": file_api_key}
        return None
