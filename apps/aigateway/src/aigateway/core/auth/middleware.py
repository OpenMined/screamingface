from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from .models import Account, BaseAccount
from .resolvers.base import IdentityResolver, Rejection

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
    """Authenticate the request against the registered resolver chain.

    INVARIANT: this function knows no credential formats. Every credential shape
    lives in an :class:`~aigateway.core.auth.resolvers.base.IdentityResolver`
    adapter registered on ``app.state.identity_resolvers``.
    """
    if not request.app.state.settings.auth_enabled:
        # INVARIANT: the escape hatch stays AHEAD of the chain — when the gateway
        # is not authenticating at all, no resolver should observe the request.
        return anonymous_account()

    resolvers: list[IdentityResolver] = getattr(request.app.state, "identity_resolvers", [])
    rejection: Rejection | None = None
    for resolver in resolvers:
        outcome = await resolver.resolve(request)
        if isinstance(outcome, Rejection):
            # WHY: record but keep going. The same `Authorization: Bearer` header
            # can hold a credential a later resolver owns, so one resolver's
            # refusal must not deny the rest their turn.
            if rejection is None:
                rejection = outcome
            continue
        if outcome is not None:
            return outcome

    if rejection is not None:
        raise HTTPException(status_code=rejection.status_code, detail=rejection.detail)
    raise HTTPException(status_code=401, detail="Missing bearer token")


CurrentAccount = Annotated[BaseAccount, Depends(current_account)]


async def current_admin_account(account: CurrentAccount) -> BaseAccount:
    if not account.is_admin:
        raise HTTPException(status_code=403, detail={"code": "admin_required"})
    return account


CurrentAdminAccount = Annotated[BaseAccount, Depends(current_admin_account)]
