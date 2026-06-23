"""Google Code Assist OAuth helpers shared by Google-backed providers.

These helpers are the same-contract pieces that any Google Code Assist provider
(``gemini-cli``, ``antigravity``) needs: token-response normalization, expiry
calculation, account-identity extraction from id_token/userinfo, and parsing of
Google's body-encoded retry-after window. They were extracted from
``gemini_provider`` (findings U5) so a second provider can reuse them without a
plugin-to-plugin import, keeping the dependency graph ``core <- provider``.

These are pure/IO-isolated helpers (identity extraction takes an injected HTTP
client factory). Provider-specific values — client id/secret, scopes, endpoint
hosts, user agents — stay in the provider packages.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from aigateway.core.errors import AuthError

GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass(frozen=True)
class AccountIdentity:
    """Google account identity in the shape stored in the credential blob.

    Distinct from ``core.oauth.identity.AccountIdentity`` (a pydantic API model
    keyed on ``sub``); this is the credential-storage value object the Google
    providers persist, keyed on ``subject`` and serialized via ``as_dict()``.
    """

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


def _string_claim(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None


def decode_jwt_claims(token: str | None) -> dict[str, Any]:
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


def identity_from_claims(claims: dict[str, Any]) -> AccountIdentity | None:
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
    identity = identity_from_claims(decode_jwt_claims(credentials.get("id_token")))
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
    return identity_from_claims(data) if isinstance(data, dict) else None


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

    token_identity = identity_from_claims(decode_jwt_claims(creds.get("id_token")))
    return token_identity.label() if token_identity is not None else None


def _expiry_from(source: dict[str, Any]) -> int | None:
    """Resolve an absolute expiry (ms) from a single creds/response dict.

    Order within the dict: absolute ms keys, then absolute seconds, then the
    relative ``expires_in`` (computed against now). Returns None if the dict
    carries no expiry signal at all.
    """
    for key in ("expires_at_ms", "expiry_date"):
        value = source.get(key)
        if isinstance(value, int | float):
            return int(value)
    value = source.get("expires_at")
    if isinstance(value, int | float):
        return int(float(value) * 1000)
    expires_in = source.get("expires_in")
    if isinstance(expires_in, int | float | str):
        try:
            return int((time.time() + int(expires_in)) * 1000)
        except (TypeError, ValueError):
            return None
    return None


def expires_at_ms(data: dict[str, Any], previous: dict[str, Any]) -> int | None:
    """Prefer the NEW response's own expiry; fall back to ``previous`` only when
    ``data`` carries no expiry signal at all.

    A Google token refresh typically returns only ``expires_in`` (no absolute
    expiry). Mixing keys across ``data`` and ``previous`` per-key (the old
    behavior) returned the STALE ``previous`` absolute expiry before ever
    reaching ``data``'s ``expires_in`` — making the freshly-refreshed token read
    as already-expired and triggering a refresh-loop (review round 2, finding A).
    """
    resolved = _expiry_from(data)
    if resolved is not None:
        return resolved
    return _expiry_from(previous)


def normalize_token_response(
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
    resolved_expiry = expires_at_ms(data, previous)
    if resolved_expiry is not None:
        creds["expires_at_ms"] = resolved_expiry

    id_token = data.get("id_token") or previous.get("id_token")
    if isinstance(id_token, str) and id_token:
        creds["id_token"] = id_token
    for key in ("scope", "account_label", "account_identity"):
        value = data.get(key, previous.get(key))
        if value:
            creds[key] = value
    return creds


# "reset after 8s" / "reset after 1m30s" / "reset after 22h11m3s" — a run of
# number+unit components (the daily-quota form is compound, not plain seconds).
_RESET_AFTER_RE = re.compile(r"reset after\s+((?:\d+(?:\.\d+)?\s*[hms])+)", re.IGNORECASE)
_RETRY_DELAY_RE = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')
_DURATION_COMPONENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([hms])", re.IGNORECASE)
_UNIT_SECONDS = {"h": 3600.0, "m": 60.0, "s": 1.0}


def compound_duration_to_seconds(token: str) -> float | None:
    """Sum a Google-style duration like ``22h11m3s`` / ``1m30s`` / ``8s`` into
    seconds. Returns ``None`` if no h/m/s component is present."""
    total = 0.0
    matched = False
    for value, unit in _DURATION_COMPONENT_RE.findall(token):
        matched = True
        total += float(value) * _UNIT_SECONDS[unit.lower()]
    return total if matched else None


def parse_google_retry_after(response_text: str, headers: Any) -> float | None:
    """Extract a retry-after delay (seconds) from a Google Code Assist 429.

    Google surfaces the reset window in the response *body* (a ``RetryInfo``
    ``retryDelay`` in seconds, or the human "reset after <duration>" phrasing
    which may be compound, e.g. ``22h11m3s`` on daily-quota exhaustion), not a
    standard ``Retry-After`` header — so the generic header parser misses it.
    Honors a real header first, then ``retryDelay``, then the prose form.
    Returns ``None`` when nothing matches (caller falls back to exponential
    backoff).
    """
    raw = headers.get("retry-after") if headers is not None else None
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    text = response_text or ""
    delay_match = _RETRY_DELAY_RE.search(text)
    if delay_match:
        return max(0.0, float(delay_match.group(1)))
    reset_match = _RESET_AFTER_RE.search(text)
    if reset_match:
        seconds = compound_duration_to_seconds(reset_match.group(1))
        if seconds is not None:
            return max(0.0, seconds)
    return None
