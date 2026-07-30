from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request

from .cloudflare_identity import (
    HEADER_USER_EMAIL,
    account_for_identity,
    identity_from_headers,
    peer_in_networks,
)
from .jwt import decode_token
from .models import Account, BaseAccount

ANONYMOUS_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000000")


def anonymous_account() -> BaseAccount:
    return Account(
        id=ANONYMOUS_ACCOUNT_ID,
        username="anonymous",
        password_hash="",
        display_name="Anonymous",
        created_at=datetime.fromtimestamp(0, UTC),
        last_login_at=None,
        is_active=True,
    )


async def current_account(request: Request) -> BaseAccount:
    """Resolve the caller for this request, per the configured auth mode.

    The single choke point every authenticated route depends on, which is why the modes branch here
    rather than in middleware: whichever mode is active, the rest of the gateway receives a real
    `Account` and needs to know nothing about how it was established.
    """
    mode = request.app.state.settings.auth_mode
    if mode == "disabled":
        return anonymous_account()
    if mode == "cloudflare_headers":
        return await _account_from_cloudflare_headers(request)
    return await _account_from_bearer_token(request)


async def _account_from_cloudflare_headers(request: Request) -> BaseAccount:
    """Resolve the caller from the identity header Envoy injects after verifying Cloudflare's token.

    INVARIANT: no-identity is a 401, never anonymous. Falling back to the anonymous account would
    turn a misconfigured mesh — Envoy bypassed, or not injecting — into a gateway that silently
    serves every unauthenticated caller as one shared principal, pooling their credentials.

    INVARIANT: the peer network is checked BEFORE the header is read. The header is only meaningful
    from a caller the deployment vouches for, so an untrusted peer is refused without its identity
    claim ever being consulted.
    """
    settings = request.app.state.settings
    if not peer_in_networks(
        request.client.host if request.client is not None else None,
        settings.allowed_networks,
    ):
        # 403, not 401: this caller is not unidentified, they are not entitled to be believed —
        # and no credential they could present would change that. The message names neither the
        # peer nor the trusted ranges, so a probe learns nothing about the topology.
        raise HTTPException(
            status_code=403,
            detail=(
                "This gateway accepts header identity only from the networks it was configured "
                "to trust."
            ),
        )
    identity = identity_from_headers(request.headers)
    if identity is None:
        raise HTTPException(
            status_code=401,
            detail=(
                f"Missing {HEADER_USER_EMAIL} — this gateway resolves the caller from the identity "
                "header the mesh gateway injects after verifying Cloudflare Access. Service-token "
                "callers are not supported in this mode."
            ),
        )
    account = await account_for_identity(identity)
    if account is None:
        raise HTTPException(status_code=401, detail="Account not found or inactive")
    return account


async def _account_from_bearer_token(request: Request) -> BaseAccount:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth_header[len("Bearer ") :]
    try:
        claims = decode_token(token, secret=request.app.state.jwt_secret)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: expired ({exc})") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    try:
        account_id = UUID(claims["sub"])
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token: malformed subject") from exc

    account = await Account.get_or_none(id=account_id)
    if account is None or not account.is_active:
        raise HTTPException(status_code=401, detail="Account not found or inactive")
    return account


CurrentAccount = Annotated[BaseAccount, Depends(current_account)]
