from __future__ import annotations

import logging

import pytest
from pydantic import SecretStr

from aigateway.core.auth.jwt_secret import (
    JWT_SECRET_ACCOUNT,
    JWT_SECRET_SERVICE,
    get_or_create_jwt_secret,
)


@pytest.mark.asyncio
async def test_env_jwt_secret_wins(fake_keychain) -> None:
    secret = await get_or_create_jwt_secret(fake_keychain, SecretStr("s" * 32))
    assert secret == "s" * 32
    assert fake_keychain.read(JWT_SECRET_SERVICE, JWT_SECRET_ACCOUNT) is None


@pytest.mark.asyncio
async def test_existing_keychain_secret_reused(fake_keychain) -> None:
    fake_keychain.write(JWT_SECRET_SERVICE, JWT_SECRET_ACCOUNT, "p" * 32)
    assert await get_or_create_jwt_secret(fake_keychain) == "p" * 32


@pytest.mark.asyncio
async def test_existing_keychain_secret_must_be_strong(fake_keychain) -> None:
    fake_keychain.write(JWT_SECRET_SERVICE, JWT_SECRET_ACCOUNT, "too-short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        await get_or_create_jwt_secret(fake_keychain)


@pytest.mark.asyncio
async def test_generates_and_logs_without_leaking_secret(fake_keychain, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        secret = await get_or_create_jwt_secret(fake_keychain)
    assert len(secret) >= 32
    assert fake_keychain.read(JWT_SECRET_SERVICE, JWT_SECRET_ACCOUNT) == secret
    assert "Generated and persisted aigateway JWT secret" in caplog.text
    assert secret not in caplog.text
