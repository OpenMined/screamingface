"""Anthropic OAuth strategy keyed by profile name.

Each profile has its own keychain entry under
`aigateway:anthropic:<profile_name>`. The token blob is the flat shape
defined in the spec (snake_case keys; expires_at_ms in milliseconds).
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from aigateway.core.credential_store import CredentialStore, get_credential_store
from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.core.oauth_base import BaseOAuthStrategy

from .oauth_config import (
    ANTHROPIC_BETA,
    ANTHROPIC_CLIENT_ID,
    ANTHROPIC_TOKEN_URL,
    ANTHROPIC_VERSION,
)

logger = logging.getLogger(__name__)


def keychain_service_for(profile_name: str) -> str:
    return f"aigateway:anthropic:{profile_name}"


_ACCOUNT = "default"  # single account inside each provider keychain entry


class AnthropicOAuth(BaseOAuthStrategy):
    def __init__(
        self,
        profile_name: str,
        *,
        credential_store: CredentialStore | None = None,
        account: str | None = None,
        http_client_factory=None,
    ) -> None:
        super().__init__(profile_name=profile_name)
        self._store = credential_store or get_credential_store()
        self._account = account if account is not None else _ACCOUNT
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )

    def keychain_service(self) -> str:
        return keychain_service_for(self.profile_name)

    def keychain_account(self) -> str:
        return self._account

    def _read_credential(self) -> dict:
        raw = self._store.read(self.keychain_service(), self.keychain_account())
        if raw is None:
            raise CredentialNotFoundError(
                f"No tokens for anthropic profile {self.profile_name!r}. "
                "Re-authenticate via Electron."
            )
        try:
            creds = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuthError(
                f"Token blob for {self.profile_name!r} is not valid JSON: {exc}"
            ) from exc
        for key in ("access_token", "refresh_token", "expires_at_ms"):
            if key not in creds:
                raise AuthError(f"Token blob missing required field {key!r}")
        return creds

    def _is_expired(self, creds: dict) -> bool:
        return time.time() * 1000 >= creds["expires_at_ms"] - (self.refresh_window_seconds * 1000)

    def _build_headers(self, creds: dict) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {creds['access_token']}",
            "anthropic-version": ANTHROPIC_VERSION,
            "anthropic-beta": ANTHROPIC_BETA,
        }

    async def _refresh_credential(self, creds: dict) -> dict:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": creds["refresh_token"],
            "client_id": ANTHROPIC_CLIENT_ID,
        }
        try:
            async with self._http_factory() as client:
                resp = await client.post(
                    ANTHROPIC_TOKEN_URL,
                    json=body,
                    headers={"content-type": "application/json"},
                )
        except httpx.RequestError as exc:
            raise AuthError(f"Refresh endpoint unreachable: {exc}") from exc

        if resp.status_code == 401:
            raise AuthError(
                f"Refresh returned 401 for profile {self.profile_name!r}. Re-auth required."
            )
        if resp.status_code != 200:
            raise AuthError(f"OAuth refresh failed status {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AuthError(f"OAuth refresh response not JSON: {exc}") from exc

        new_creds = self._convert_refresh_response(data)
        self._write_to_store(new_creds)
        return new_creds

    def _convert_refresh_response(self, data: dict) -> dict:
        for required in ("access_token", "refresh_token", "expires_in"):
            if required not in data:
                raise AuthError(f"OAuth refresh response missing {required!r}")
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at_ms": int((time.time() + int(data["expires_in"])) * 1000),
            "token_type": data.get("token_type", "Bearer"),
        }

    def _write_to_store(self, creds: dict) -> None:
        self._store.write(self.keychain_service(), self.keychain_account(), json.dumps(creds))


async def exchange_authorization_code(
    code: str,
    code_verifier: str,
    *,
    redirect_uri: str | None = None,
    http_client_factory=None,
) -> dict:
    """Exchange an authorization code for tokens. Used by the OAuth callback handler.

    ``redirect_uri`` must match the one sent to ``/authorize`` in the same flow.
    Some OAuth servers (including Anthropic's) reject the exchange when the two
    don't match. When omitted we don't send it (legacy behavior; works for
    servers that don't require it).
    """
    factory = http_client_factory or (lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0)))
    body: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "client_id": ANTHROPIC_CLIENT_ID,
    }
    if redirect_uri:
        body["redirect_uri"] = redirect_uri
    async with factory() as client:
        resp = await client.post(
            ANTHROPIC_TOKEN_URL,
            json=body,
            headers={"content-type": "application/json"},
        )
    if resp.status_code != 200:
        # Log the full request/response detail for diagnosing OAuth failures.
        # Token endpoint errors are usually wrong content-type, missing
        # redirect_uri match, or scope/grant_type mismatches — the body tells
        # us which.
        logger.error(
            "Anthropic token exchange failed: status=%d url=%s sent_keys=%s response=%s",
            resp.status_code,
            ANTHROPIC_TOKEN_URL,
            sorted(body.keys()),
            resp.text[:1000],
        )
        raise AuthError(
            f"Authorization code exchange failed (HTTP {resp.status_code}): {resp.text[:500]}"
        )
    data = resp.json()
    for required in ("access_token", "refresh_token", "expires_in"):
        if required not in data:
            raise AuthError(f"Authorization code response missing {required!r}")
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at_ms": int((time.time() + int(data["expires_in"])) * 1000),
        "token_type": data.get("token_type", "Bearer"),
    }
