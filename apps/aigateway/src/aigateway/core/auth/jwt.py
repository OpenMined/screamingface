from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt


def encode_token(
    *,
    account_id: str,
    username: str,
    secret: str,
    ttl_seconds: int,
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl_seconds)
    claims = {
        "sub": account_id,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(claims, secret, algorithm="HS256"), expires_at


def decode_token(token: str, secret: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ["exp", "iat", "sub"]},
    )
