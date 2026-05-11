from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import SecretStr
from starlette.responses import Response
from tortoise.exceptions import IntegrityError

from ..core.auth.models import Account
from ..core.auth.passwords import hash_password
from ..core.auth.provisioning import PROVISIONING_HEADER, verify_provisioning_token
from ..core.auth.schemas import AccountOut, CreateAccountRequest

logger = logging.getLogger(__name__)


def _audit_provisioning_attempt(request: Request, status_code: int) -> None:
    if status_code == 201:
        username = getattr(request.state, "provisioned_username", None)
        if username is None:
            logger.info("account_created")
        else:
            logger.info("account_created username=%s", username)
        return
    username = getattr(request.state, "provisioning_username", None)
    if username is None:
        logger.info("provisioning_token_rejected status_code=%d", status_code)
    else:
        logger.info("provisioning_token_rejected status_code=%d username=%s", status_code, username)


class ProvisioningAuditRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def audited_handler(request: Request) -> Response:
            try:
                response = await original_handler(request)
            except HTTPException as exc:
                _audit_provisioning_attempt(request, exc.status_code)
                raise
            except RequestValidationError:
                _audit_provisioning_attempt(request, 422)
                raise
            except Exception:
                _audit_provisioning_attempt(request, 500)
                raise
            _audit_provisioning_attempt(request, response.status_code)
            return response

        return audited_handler


router = APIRouter(route_class=ProvisioningAuditRoute)

_BAD_TOKEN = {"code": "invalid_provisioning_token", "message": "Invalid provisioning token"}


async def require_provisioning_token(
    request: Request,
    token: Annotated[str | None, Header(alias=PROVISIONING_HEADER)] = None,
) -> SecretStr:
    expected = request.app.state.settings.provisioning_token
    if expected is None:
        raise HTTPException(status_code=503, detail="Provisioning is disabled")
    if not verify_provisioning_token(token, expected):
        raise HTTPException(status_code=401, detail=_BAD_TOKEN)
    return expected


@router.post("/v1/accounts", status_code=201, response_model=AccountOut)
async def create_account(
    request: Request,
    body: CreateAccountRequest,
    _token: Annotated[SecretStr, Depends(require_provisioning_token)],
) -> AccountOut:
    request.state.provisioning_username = body.username
    password_hash = await hash_password(body.password)
    try:
        account = await Account.create(
            username=body.username,
            password_hash=password_hash,
            display_name=body.display_name,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="username already exists") from exc

    request.state.provisioned_username = account.username
    return AccountOut.model_validate(account)
