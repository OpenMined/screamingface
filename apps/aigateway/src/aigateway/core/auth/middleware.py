from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request

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
    if not request.app.state.settings.auth_enabled:
        return anonymous_account()

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


async def current_admin_account(account: CurrentAccount) -> BaseAccount:
    if not account.is_admin:
        raise HTTPException(status_code=403, detail={"code": "admin_required"})
    return account


CurrentAdminAccount = Annotated[BaseAccount, Depends(current_admin_account)]
