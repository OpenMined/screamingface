from __future__ import annotations

import asyncio
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
async def test_bootstrap_logs_generated_password_once(db, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        await ensure_admin_account(None)
        await ensure_admin_account(None)
    messages = [record.getMessage() for record in caplog.records]
    bootstraps = [message for message in messages if "Bootstrap admin password:" in message]
    assert len(bootstraps) == 1
    generated = bootstraps[0].split(": ", 1)[1]
    admin = await Account.get(username="admin")
    assert await verify_password(generated, admin.password_hash)


@pytest.mark.asyncio
async def test_bootstrap_concurrent_race_logs_one_password(db, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        await asyncio.gather(*[ensure_admin_account(None) for _ in range(4)])
    assert await Account.all().count() == 1
    bootstraps = [
        record.getMessage()
        for record in caplog.records
        if "Bootstrap admin password:" in record.getMessage()
    ]
    assert len(bootstraps) == 1
    generated = bootstraps[0].split(": ", 1)[1]
    admin = await Account.get(username="admin")
    assert await verify_password(generated, admin.password_hash)
