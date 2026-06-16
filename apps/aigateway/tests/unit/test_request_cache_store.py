from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from tortoise import Tortoise

from aigateway.core.request_cache.models import RequestCacheEntry
from aigateway.core.request_cache.store import (
    RequestCacheWrite,
    TortoiseRequestCacheStore,
)
from aigateway.core.secrets.local import LocalSecretStore
from aigateway.db import build_tortoise_config

_TEST_KEY = bytes(range(32))


def _write(key_hash: str = "k" * 64, *, ttl_seconds: int = 600, **overrides) -> RequestCacheWrite:
    values = {
        "key_hash": key_hash,
        "key_version": "aigw-chat-cache-v1",
        "account_id": "acct-1",
        "profile_name": "default",
        "prompt_hash": "p" * 64,
        "provider": "anthropic",
        "model": "anthropic/claude-haiku-4-5",
        "response": {"id": "x", "choices": [{"message": {"content": "SECRET-ANSWER"}}]},
        "response_size_bytes": 64,
        "expires_at": datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    }
    values.update(overrides)
    return RequestCacheWrite(**values)


@pytest_asyncio.fixture
async def cache_store(tmp_path):
    db_path = tmp_path / "cache-test.sqlite3"
    await Tortoise.close_connections()
    await Tortoise.init(
        config=build_tortoise_config(f"sqlite://{db_path}"),
        _enable_global_fallback=True,
    )
    await Tortoise.generate_schemas()
    try:
        # Inject the secret store directly (the process-wide active store is only
        # installed by the app lifespan, which this unit fixture does not run).
        yield TortoiseRequestCacheStore(secret_store=LocalSecretStore(_TEST_KEY))
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_set_then_get_round_trips_response(cache_store) -> None:
    entry = _write()
    await cache_store.set(entry)
    got = await cache_store.get(entry.key_hash)
    assert got == entry.response


@pytest.mark.asyncio
async def test_get_missing_returns_none(cache_store) -> None:
    assert await cache_store.get("missing" + "0" * 57) is None


@pytest.mark.asyncio
async def test_expired_entry_returns_none(cache_store) -> None:
    entry = _write(ttl_seconds=-5)
    await cache_store.set(entry)
    assert await cache_store.get(entry.key_hash) is None


@pytest.mark.asyncio
async def test_s_maxage_rejects_older_entries(cache_store) -> None:
    entry = _write()
    await cache_store.set(entry)
    # Entry was just created: a generous max age accepts it...
    assert await cache_store.get(entry.key_hash, max_age_seconds=60) == entry.response
    # ...but a zero-second freshness window rejects it even though unexpired.
    row = await RequestCacheEntry.get(key_hash=entry.key_hash)
    row.created_at = datetime.now(UTC) - timedelta(seconds=30)
    await row.save(update_fields=["created_at"])
    assert await cache_store.get(entry.key_hash, max_age_seconds=10) is None


@pytest.mark.asyncio
async def test_db_row_does_not_contain_plaintext_response(cache_store) -> None:
    entry = _write()
    await cache_store.set(entry)
    row = await RequestCacheEntry.get(key_hash=entry.key_hash)
    assert "SECRET-ANSWER" not in row.response_ciphertext
    assert json.dumps(entry.response) != row.response_ciphertext


@pytest.mark.asyncio
async def test_duplicate_write_updates_existing_row(cache_store) -> None:
    first = _write()
    await cache_store.set(first)
    second = _write(response={"id": "y", "choices": []})
    await cache_store.set(second)
    assert await RequestCacheEntry.filter(key_hash=first.key_hash).count() == 1
    assert await cache_store.get(first.key_hash) == second.response


@pytest.mark.asyncio
async def test_hit_metadata_updated_on_get(cache_store) -> None:
    entry = _write()
    await cache_store.set(entry)
    await cache_store.get(entry.key_hash)
    await cache_store.get(entry.key_hash)
    row = await RequestCacheEntry.get(key_hash=entry.key_hash)
    assert row.hit_count == 2
    assert row.last_hit_at is not None


@pytest.mark.asyncio
async def test_delete_expired_removes_only_expired(cache_store) -> None:
    # Write both entries live, then age one directly — set() itself purges
    # expired rows opportunistically, so an already-dead write never persists.
    live = _write("l" * 64, ttl_seconds=600)
    dead = _write("d" * 64, ttl_seconds=600)
    await cache_store.set(live)
    await cache_store.set(dead)
    row = await RequestCacheEntry.get(key_hash=dead.key_hash)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=5)
    await row.save(update_fields=["expires_at"])

    deleted = await cache_store.delete_expired()
    assert deleted == 1
    assert await RequestCacheEntry.filter(key_hash=live.key_hash).exists()
    assert not await RequestCacheEntry.filter(key_hash=dead.key_hash).exists()


@pytest.mark.asyncio
async def test_set_purges_already_expired_rows_opportunistically(cache_store) -> None:
    dead = _write("d" * 64, ttl_seconds=-5)
    await cache_store.set(dead)
    assert not await RequestCacheEntry.filter(key_hash=dead.key_hash).exists()


@pytest.mark.asyncio
async def test_corrupt_ciphertext_returns_none_and_deletes(cache_store) -> None:
    entry = _write()
    await cache_store.set(entry)
    row = await RequestCacheEntry.get(key_hash=entry.key_hash)
    row.response_ciphertext = "not-valid-ciphertext"
    await row.save(update_fields=["response_ciphertext"])
    assert await cache_store.get(entry.key_hash) is None
    assert not await RequestCacheEntry.filter(key_hash=entry.key_hash).exists()
