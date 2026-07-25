"""Local password-session credentials — the HS256 JWT minted by ``/v1/auth/login``.

STORY: as an operator running the gateway without any federated IdP, I log in
with a username and password and use the returned token, exactly as before.
"""

from __future__ import annotations

from uuid import UUID

import jwt
from fastapi import Request

from ..jwt import decode_token
from ..models import Account
from .base import Rejection, Resolution

_BEARER_PREFIX = "Bearer "

#: The algorithm this resolver claims. Cloudflare Access signs RS256, gateway API
#: keys are not JWTs at all — so the JOSE ``alg`` header is a clean, cheap
#: discriminator for routing a bearer token to the right resolver.
_ALGORITHM = "HS256"


def bearer_token(request: Request) -> str | None:
    """Return the bearer token from ``Authorization``, or None when absent."""
    header = request.headers.get("Authorization", "")
    if not header.startswith(_BEARER_PREFIX):
        return None
    return header[len(_BEARER_PREFIX) :]


class LocalJwtResolver:
    """Authenticate the gateway's own session token."""

    name = "local_jwt"

    async def resolve(self, request: Request) -> Resolution:
        token = bearer_token(request)
        if token is None:
            return None

        try:
            algorithm = jwt.get_unverified_header(token).get("alg")
        except jwt.InvalidTokenError as exc:
            # Not decodable as a JWT at all. No other resolver wants a bearer
            # token this broken, so claim it and report the real reason.
            return Rejection(detail=f"Invalid token: {exc}")

        if algorithm != _ALGORITHM:
            # WHY: abstain rather than reject — this is how a Cloudflare Access
            # assertion presented in `Authorization: Bearer` reaches its own
            # resolver. Routing on the *unverified* header is safe because
            # `decode_token` still pins algorithms=["HS256"], so an attacker
            # cannot downgrade or confuse the algorithm by editing it.
            return None

        try:
            claims = decode_token(token, secret=request.app.state.jwt_secret)
        except jwt.ExpiredSignatureError as exc:
            return Rejection(detail=f"Invalid token: expired ({exc})")
        except jwt.InvalidTokenError as exc:
            return Rejection(detail=f"Invalid token: {exc}")

        try:
            account_id = UUID(claims["sub"])
        except (TypeError, ValueError):
            return Rejection(detail="Invalid token: malformed subject")

        account = await Account.get_or_none(id=account_id)
        if account is None or not account.is_active:
            return Rejection(detail="Account not found or inactive")
        return account
