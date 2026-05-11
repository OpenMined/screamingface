from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from ..core.auth.jwt import encode_token
from ..core.auth.middleware import CurrentAccount
from ..core.auth.models import Account
from ..core.auth.passwords import verify_password_or_dummy
from ..core.auth.schemas import AccountOut, LoginRequest, LoginResponse

router = APIRouter()

_INVALID_CREDENTIALS = {"code": "invalid_credentials", "message": "Invalid username or password"}


@router.post("/v1/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    """Authenticate an account and return a stateless JWT session.

    Inactive accounts return 423. This leaks that a username exists, but v1 is
    single-tenant/admin-provisioned and the distinction is operationally useful.
    """
    account = await Account.get_or_none(username=body.username)
    password_hash = account.password_hash if account is not None else None
    password_ok = await verify_password_or_dummy(body.password, password_hash)
    if account is None or not password_ok:
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)
    if not account.is_active:
        raise HTTPException(status_code=423, detail={"code": "account_locked"})

    account.last_login_at = datetime.now(UTC)
    await account.save(update_fields=["last_login_at"])
    token, expires_at = encode_token(
        account_id=str(account.id),
        username=account.username,
        secret=request.app.state.jwt_secret,
        ttl_seconds=request.app.state.settings.jwt_ttl_seconds,
    )
    return LoginResponse(
        token=token,
        expires_at=expires_at,
        account=AccountOut.model_validate(account),
    )


@router.get("/v1/auth/me", response_model=AccountOut)
async def me(current: CurrentAccount) -> AccountOut:
    return AccountOut.model_validate(current)
