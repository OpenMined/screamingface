from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from aigateway.core.credential_blob.store import CredentialBlobStore, ORMStore
from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.core.oauth_base import BaseOAuthStrategy

from .oauth_config import GEMINI_CLIENT_ID, GEMINI_CLIENT_SECRET, GEMINI_TOKEN_URL

_ACCOUNT = "default"
GEMINI_PROFILE_HEADER = "X-AIGW-Gemini-Profile"
GEMINI_USER_AGENT = "GeminiCLI/0.42.0/gemini-2.5-flash (aigateway)"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass(frozen=True)
class AccountIdentity:
    email: str | None = None
    name: str | None = None
    subject: str | None = None

    def label(self) -> str | None:
        return self.email or self.name or self.subject

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "email": self.email,
                "name": self.name,
                "subject": self.subject,
            }.items()
            if value
        }


def credential_service_for(profile_name: str) -> str:
    return f"aigateway:gemini:{profile_name}"


def _string_claim(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None


def _decode_jwt_claims(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _identity_from_claims(claims: dict[str, Any]) -> AccountIdentity | None:
    identity = AccountIdentity(
        email=_string_claim(claims, "email"),
        name=_string_claim(claims, "name"),
        subject=_string_claim(claims, "sub"),
    )
    return identity if identity.label() else None


async def extract_account_identity(
    credentials: dict[str, Any],
    *,
    http_client_factory=None,
) -> AccountIdentity | None:
    identity = _identity_from_claims(_decode_jwt_claims(credentials.get("id_token")))
    if identity is not None:
        return identity

    access_token = credentials.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return None

    factory = http_client_factory or (lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0)))
    try:
        async with factory() as client:
            resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.RequestError:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return None
    return _identity_from_claims(data) if isinstance(data, dict) else None


def account_label_from_credentials(creds: dict[str, Any]) -> str | None:
    label = creds.get("account_label")
    if isinstance(label, str) and label:
        return label

    identity_data = creds.get("account_identity")
    if isinstance(identity_data, dict):
        identity = AccountIdentity(
            email=_string_claim(identity_data, "email"),
            name=_string_claim(identity_data, "name"),
            subject=_string_claim(identity_data, "subject"),
        )
        if identity.label():
            return identity.label()

    token_identity = _identity_from_claims(_decode_jwt_claims(creds.get("id_token")))
    return token_identity.label() if token_identity is not None else None


def _expires_at_ms(data: dict[str, Any], previous: dict[str, Any]) -> int | None:
    for key in ("expires_at_ms", "expiry_date"):
        value = data.get(key, previous.get(key))
        if isinstance(value, int | float):
            return int(value)
    value = data.get("expires_at", previous.get("expires_at"))
    if isinstance(value, int | float):
        return int(float(value) * 1000)
    expires_in = data.get("expires_in")
    if isinstance(expires_in, int | float | str):
        try:
            return int((time.time() + int(expires_in)) * 1000)
        except (TypeError, ValueError):
            return None
    return None


def _normalize_token_response(
    data: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    previous = previous or {}
    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise AuthError("Google OAuth response missing 'access_token'")

    refresh_token = data.get("refresh_token") or previous.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise AuthError("Google OAuth response missing 'refresh_token'")

    creds: dict[str, Any] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": data.get("token_type", previous.get("token_type", "Bearer")),
    }
    expires_at_ms = _expires_at_ms(data, previous)
    if expires_at_ms is not None:
        creds["expires_at_ms"] = expires_at_ms

    id_token = data.get("id_token") or previous.get("id_token")
    if isinstance(id_token, str) and id_token:
        creds["id_token"] = id_token
    for key in ("scope", "account_label", "account_identity"):
        value = data.get(key, previous.get(key))
        if value:
            creds[key] = value
    return creds


class GeminiOAuth(BaseOAuthStrategy):
    def __init__(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
        account: str | None = None,
        http_client_factory=None,
    ) -> None:
        super().__init__(profile_name=profile_name)
        self._store = credential_store or ORMStore()
        self._account = account if account is not None else _ACCOUNT
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )

    def credential_service(self) -> str:
        return credential_service_for(self.profile_name)

    def credential_account(self) -> str:
        return self._account

    async def _read_credential(self) -> dict[str, Any]:
        raw = await self._store.read(self.credential_service(), self.credential_account())
        if raw is None:
            raise CredentialNotFoundError(
                f"No tokens for gemini profile {self.profile_name!r}. Re-authenticate via Electron."
            )
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuthError(
                f"Token blob for {self.profile_name!r} is not valid JSON: {exc}"
            ) from exc
        if not isinstance(loaded, dict):
            raise AuthError(f"Token blob for {self.profile_name!r} is not a JSON object")
        return _normalize_token_response(loaded, loaded)

    def _is_expired(self, creds: dict[str, Any]) -> bool:
        expires_at_ms = creds.get("expires_at_ms")
        if not isinstance(expires_at_ms, int | float) or expires_at_ms <= 0:
            return False
        return time.time() * 1000 >= expires_at_ms - (self.refresh_window_seconds * 1000)

    def _build_headers(self, creds: dict[str, Any]) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {creds['access_token']}",
            "User-Agent": GEMINI_USER_AGENT,
            GEMINI_PROFILE_HEADER: self.profile_name,
        }

    async def _refresh_credential(self, creds: dict[str, Any]) -> dict[str, Any]:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": creds["refresh_token"],
            "client_id": GEMINI_CLIENT_ID,
            "client_secret": GEMINI_CLIENT_SECRET,
        }
        try:
            async with self._http_factory() as client:
                resp = await client.post(
                    GEMINI_TOKEN_URL,
                    data=body,
                    headers={"content-type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as exc:
            raise AuthError(f"Google token endpoint unreachable: {exc}") from exc

        if resp.status_code == 401:
            raise AuthError(
                f"Refresh returned 401 for profile {self.profile_name!r}. Re-auth required."
            )
        if resp.status_code != 200:
            raise AuthError(
                f"Google OAuth refresh failed status {resp.status_code}: {resp.text[:500]}"
            )
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AuthError(f"Google OAuth refresh response not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise AuthError("Google OAuth refresh response is not a JSON object")

        refreshed = _normalize_token_response(data, creds)
        await self._write_to_store(refreshed)
        return refreshed

    async def _write_to_store(self, creds: dict[str, Any]) -> None:
        await self._store.write(
            self.credential_service(), self.credential_account(), json.dumps(creds)
        )


async def exchange_authorization_code(
    code: str,
    code_verifier: str,
    *,
    redirect_uri: str,
    http_client_factory=None,
) -> dict[str, Any]:
    factory = http_client_factory or (lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0)))
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": GEMINI_CLIENT_ID,
        "client_secret": GEMINI_CLIENT_SECRET,
        "code_verifier": code_verifier,
    }
    try:
        async with factory() as client:
            resp = await client.post(
                GEMINI_TOKEN_URL,
                data=body,
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
    except httpx.RequestError as exc:
        raise AuthError(f"Google authorization code exchange unreachable: {exc}") from exc

    if resp.status_code != 200:
        raise AuthError(f"Google authorization code exchange failed (HTTP {resp.status_code})")
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise AuthError(f"Google authorization code response not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AuthError("Google authorization code response is not a JSON object")

    creds = _normalize_token_response(data)
    identity = await extract_account_identity(creds, http_client_factory=http_client_factory)
    if identity is not None:
        creds["account_identity"] = identity.as_dict()
        label = identity.label()
        if label is not None:
            creds["account_label"] = label
    return creds
