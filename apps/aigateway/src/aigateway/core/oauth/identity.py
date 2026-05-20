from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel, Field


class AccountIdentity(BaseModel):
    sub: str | None = None
    email: str | None = None
    name: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def has_identity(self) -> bool:
        return bool(self.sub or self.email or self.name)

    def label(self) -> str | None:
        return self.email or self.name or self.sub


def decode_jwt_claims(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def identity_from_claims(claims: dict[str, Any]) -> AccountIdentity | None:
    identity = AccountIdentity(
        sub=_string_claim(claims, "sub"),
        email=_string_claim(claims, "email"),
        name=_string_claim(claims, "name"),
        raw=claims,
    )
    return identity if identity.has_identity() else None


def identity_from_id_token(token: str | None) -> AccountIdentity | None:
    return identity_from_claims(decode_jwt_claims(token))


def _string_claim(claims: dict[str, Any], key: str) -> str | None:
    value = claims.get(key)
    return value if isinstance(value, str) and value else None
