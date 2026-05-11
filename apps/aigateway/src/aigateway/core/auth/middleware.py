from __future__ import annotations

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request

from .jwt import decode_token
from .models import Account


async def current_account(request: Request) -> Account:
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


CurrentAccount = Annotated[Account, Depends(current_account)]
