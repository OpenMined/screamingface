from __future__ import annotations

import pytest
import pytest_asyncio
from tortoise import Tortoise

from aigateway.core.credential_blob.store import ORMStore
from aigateway.db import build_tortoise_config


@pytest_asyncio.fixture
async def orm_store(credential_blobs):
    await Tortoise.close_connections()
    await Tortoise.init(
        config=build_tortoise_config(f"sqlite://{credential_blobs.db_path}"),
        _enable_global_fallback=True,
    )
    try:
        yield ORMStore()
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_orm_store_round_trip(credential_blobs, orm_store) -> None:
    assert await orm_store.read("service", "account") is None
    await orm_store.write("service", "account", "secret")
    assert await orm_store.read("service", "account") == "secret"

    await orm_store.write("service", "account", "updated")
    assert credential_blobs.read("service", "account") == "updated"

    await orm_store.delete("service", "account")
    assert await orm_store.read("service", "account") is None


@pytest.mark.asyncio
async def test_orm_store_delete_is_idempotent(credential_blobs, orm_store) -> None:
    await orm_store.delete("missing", "account")
    assert credential_blobs.read("missing", "account") is None
