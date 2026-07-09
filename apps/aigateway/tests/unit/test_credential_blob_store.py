from __future__ import annotations

import pytest
import pytest_asyncio
from tortoise import Tortoise

from aigateway.core.credential_blob.store import ORMStore
from aigateway.core.secrets.local import LocalSecretStore
from aigateway.db import build_tortoise_config

_TEST_KEY = bytes(range(32))


@pytest_asyncio.fixture
async def orm_store(credential_blobs):
    await Tortoise.close_connections()
    await Tortoise.init(
        config=build_tortoise_config(f"sqlite://{credential_blobs.db_path}"),
        _enable_global_fallback=True,
    )
    try:
        # Inject the secret store directly (the process-wide active store is only
        # installed by the app lifespan, which this unit fixture does not run).
        yield ORMStore(secret_store=LocalSecretStore(_TEST_KEY))
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_orm_store_round_trip(credential_blobs, orm_store) -> None:
    assert await orm_store.read("service", "account") is None
    await orm_store.write("service", "account", "secret")
    assert await orm_store.read("service", "account") == "secret"

    await orm_store.write("service", "account", "updated")
    assert await orm_store.read("service", "account") == "updated"

    # The value is stored encrypted, not as plaintext.
    raw = credential_blobs.read_raw("service", "account")
    assert raw is not None
    assert raw.startswith("v1:")
    assert "updated" not in raw

    await orm_store.delete("service", "account")
    assert await orm_store.read("service", "account") is None


@pytest.mark.asyncio
async def test_orm_store_persists_ciphertext_version(credential_blobs, orm_store) -> None:
    await orm_store.write("svc", "acc", "value")
    assert credential_blobs.read_ciphertext_version("svc", "acc") == "v1"


@pytest.mark.asyncio
async def test_orm_store_reads_legacy_plaintext(credential_blobs, orm_store) -> None:
    # A row written before SF-221 holds plaintext JSON (no v1: prefix).
    legacy = '{"access_token":"legacy-plaintext"}'
    credential_blobs.write_raw("legacy", "account", legacy)
    assert await orm_store.read("legacy", "account") == legacy

    # Next write upgrades it to ciphertext.
    await orm_store.write("legacy", "account", legacy)
    raw = credential_blobs.read_raw("legacy", "account")
    assert raw.startswith("v1:")
    assert await orm_store.read("legacy", "account") == legacy


@pytest.mark.asyncio
async def test_orm_store_delete_is_idempotent(credential_blobs, orm_store) -> None:
    await orm_store.delete("missing", "account")
    assert credential_blobs.read("missing", "account") is None


@pytest.mark.asyncio
async def test_orm_store_mutate_can_delete_existing_blob(credential_blobs, orm_store) -> None:
    await orm_store.write("service", "account", "secret")

    await orm_store.mutate("service", "account", lambda current: None)

    assert await orm_store.read("service", "account") is None
    assert credential_blobs.read_raw("service", "account") is None


@pytest.mark.asyncio
async def test_orm_store_mutate_delete_missing_blob_is_noop(credential_blobs, orm_store) -> None:
    await orm_store.mutate("service", "account", lambda current: None)

    assert await orm_store.read("service", "account") is None
