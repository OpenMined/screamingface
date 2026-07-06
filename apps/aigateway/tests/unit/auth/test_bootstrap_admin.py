from __future__ import annotations

import logging

import pytest
from pydantic import SecretStr

from aigateway.core.auth.bootstrap_admin import ensure_admin_account
from aigateway.core.auth.models import Account
from aigateway.core.auth.passwords import verify_password


@pytest.mark.asyncio
async def test_env_admin_password_creates_loginable_admin(db) -> None:
    await ensure_admin_account(SecretStr("admin-password"))
    admin = await Account.get(username="admin")
    assert await verify_password("admin-password", admin.password_hash)


@pytest.mark.asyncio
async def test_missing_admin_password_is_not_generated_or_logged(db, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="AIGATEWAY_ADMIN_PASSWORD"):
            await ensure_admin_account(None)

    messages = [record.getMessage() for record in caplog.records]
    assert not any("Bootstrap admin password" in message for message in messages)
    assert await Account.get_or_none(username="admin") is None


@pytest.mark.asyncio
async def test_missing_admin_password_race_creates_no_account_or_secret_log(db, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        for _ in range(4):
            with pytest.raises(RuntimeError, match="AIGATEWAY_ADMIN_PASSWORD"):
                await ensure_admin_account(None)

    assert await Account.all().count() == 0
    assert not any("Bootstrap admin password" in record.getMessage() for record in caplog.records)
