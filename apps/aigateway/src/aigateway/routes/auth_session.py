from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from ..core.auth.jwt import encode_token
from ..core.auth.middleware import CurrentAccount
from ..core.auth.models import Account
from ..core.auth.passwords import verify_password_or_dummy
from ..core.auth.schemas import AccountOut, LoginRequest, LoginResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_INVALID_CREDENTIALS = {"code": "invalid_credentials", "message": "Invalid username or password"}


@router.post("/v1/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    """Authenticate an account and return a stateless JWT session.

    Inactive accounts receive the same generic 401 as bad credentials (no
    account-status disclosure, per OWASP); the refusal is logged server-side.
    """
    account = await Account.get_or_none(username=body.username)
    password_hash = account.password_hash if account is not None else None
    password_ok = await verify_password_or_dummy(body.password, password_hash)
    if account is None or not password_ok:
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)
    if not account.is_active:
        # SF-335: do NOT disclose account status to the client (OWASP: respond
        # generically). Still refuse to issue a session; a server-side log keeps
        # ops visibility without the 423 enumeration oracle.
        logger.info("login refused for inactive account username=%s", account.username)
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)

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
