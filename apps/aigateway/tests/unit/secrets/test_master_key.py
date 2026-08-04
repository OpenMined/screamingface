from __future__ import annotations

import base64
import os

import pytest
import pytest_asyncio
from pydantic import SecretStr
from tortoise import Tortoise

from aigateway.config import Settings
from aigateway.core.secrets.master_key import get_or_create_master_key
from aigateway.core.secrets.models import SecretMasterKey
from aigateway.db import build_tortoise_config


@pytest_asyncio.fixture
async def db(credential_blobs):
    await Tortoise.close_connections()
    await Tortoise.init(
        config=build_tortoise_config(f"sqlite://{credential_blobs.db_path}"),
        _enable_global_fallback=True,
    )
    try:
        yield
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_env_key_returns_raw_bytes() -> None:
    raw = os.urandom(32)
    key = SecretStr(base64.b64encode(raw).decode())
    assert await get_or_create_master_key(key) == raw


@pytest.mark.asyncio
async def test_env_key_bad_base64_raises() -> None:
    with pytest.raises(RuntimeError, match="base64"):
        await get_or_create_master_key(SecretStr("not!valid!base64!"))


@pytest.mark.asyncio
async def test_env_key_wrong_length_raises() -> None:
    short = SecretStr(base64.b64encode(os.urandom(16)).decode())
    with pytest.raises(RuntimeError, match="32 bytes"):
        await get_or_create_master_key(short)


def test_empty_secret_key_setting_selects_database_managed_key() -> None:
    assert Settings(**{"_env_file": None, "AIGATEWAY_SECRET_KEY": ""}).secret_key is None


def test_blank_nonempty_secret_key_setting_remains_invalid_key_material() -> None:
    assert Settings(**{"_env_file": None, "AIGATEWAY_SECRET_KEY": " "}).secret_key is not None


@pytest.mark.asyncio
async def test_autogen_persists_and_is_idempotent(db) -> None:
    assert await SecretMasterKey.all().count() == 0

    first = await get_or_create_master_key(None)
    assert len(first) == 32
    assert await SecretMasterKey.all().count() == 1

    # Second call must return the SAME key and not create a duplicate row.
    second = await get_or_create_master_key(None)
    assert second == first
    assert await SecretMasterKey.all().count() == 1


@pytest.mark.asyncio
async def test_persisted_key_decodes_to_32_bytes(db) -> None:
    key = await get_or_create_master_key(None)
    row = await SecretMasterKey.get(provider="local", version="v1")
    assert base64.b64decode(row.key_material) == key


@pytest.mark.asyncio
async def test_autogen_integrityerror_rereads_winner(db, monkeypatch) -> None:
    # Simulate concurrent first boot: a "winner" row already exists, but this
    # caller's filter().first() returns None, so it attempts create(), hits the
    # unique_together violation, and must re-read + return the winner's key
    # (master_key.py race-recovery branch).
    winner_raw = os.urandom(32)
    await SecretMasterKey.create(
        provider="local", version="v1", key_material=base64.b64encode(winner_raw).decode()
    )

    class _EmptyQS:
        async def first(self):
            return None

    monkeypatch.setattr(SecretMasterKey, "filter", classmethod(lambda cls, **kw: _EmptyQS()))

    got = await get_or_create_master_key(None)
    assert got == winner_raw

    monkeypatch.undo()
    assert await SecretMasterKey.all().count() == 1
