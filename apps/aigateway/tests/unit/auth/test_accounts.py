from __future__ import annotations

import pytest
from tortoise.exceptions import IntegrityError

from aigateway.core.auth.models import Account


@pytest.mark.asyncio
async def test_account_crud(db) -> None:
    account = await Account.create(username="alice", password_hash="hash")
    fetched = await Account.get(username="alice")
    assert fetched.id == account.id
    assert fetched.is_active


@pytest.mark.asyncio
async def test_username_unique(db) -> None:
    await Account.create(username="alice", password_hash="hash")
    with pytest.raises(IntegrityError):
        await Account.create(username="alice", password_hash="hash")
