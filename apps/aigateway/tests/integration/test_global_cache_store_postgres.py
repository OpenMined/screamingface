"""PostgreSQL evidence for the global request cache (OME-305 plan §9).

Plan §9 states plainly that SQLite success is NOT evidence for these three properties, and it is
right: each one behaves differently on Postgres.

1. **Create-only conflicts.** SQLite raises the unique violation and carries on. Postgres aborts the
   whole transaction the violation happened in, so every later statement fails until rollback.
   ``set_if_absent`` scopes its insert in a savepoint so a lost race cannot poison its caller.
2. **The nullable-expiry migration.** SQLite has no ``ALTER COLUMN`` and rebuilds the table (losing
   its indexes — see migration 0009). Postgres emits ``ALTER COLUMN ... DROP NOT NULL`` and keeps
   everything. Both halves need checking on the dialect that takes that path.
3. **Atomic hit metadata.** SQLite serializes writers, which hides a lost update entirely — a
   read-modify-write increment *passes* there. Postgres runs the writers concurrently: the same
   defect recorded 3 of 20 hits when this test was falsified against it.

Run with: ``AIGW_TEST_PG=1 uv run pytest -m needs_postgres``
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import asyncpg  # type: ignore[import-untyped]
import pytest
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
from tortoise.transactions import in_transaction

from aigateway.core.request_cache.models import RequestCacheEntry
from aigateway.core.request_cache.store import (
    GLOBAL_SENTINEL,
    GlobalRequestCacheWrite,
    TortoiseRequestCacheStore,
)
from aigateway.core.secrets.local import LocalSecretStore
from aigateway.db import close_db, init_db

pytestmark = pytest.mark.needs_postgres

_APP_DIR = Path(__file__).resolve().parents[2]
_TEST_KEY = bytes(range(32))
_KEY_VERSION_V2 = "aigw-global-chat-cache-v2"
_TABLE = "request_cache_entries"
_V1_KEY_HASH = "a" * 64
_V1_RESPONSE = {"id": "cmpl-v1", "choices": [{"message": {"content": "V1-ANSWER"}}]}


def _database_url(postgres: PostgresContainer) -> str:
    return (
        f"postgres://{postgres.username}:{quote(postgres.password, safe='')}"
        f"@{postgres.get_container_host_ip()}:{postgres.get_exposed_port(5432)}"
        f"/{postgres.dbname}"
    )


def _migrate(database_url: str, *target: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "tortoise", "-c", "aigateway.db.TORTOISE_CONFIG", "migrate"]
    return subprocess.run(
        [*command, *target],
        cwd=_APP_DIR,
        env={**os.environ, "AIGATEWAY_DATABASE_URL": database_url},
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def migrated_postgres() -> Generator[str, None, None]:
    """One container, migrated to head — the deployed schema, not ``generate_schemas``."""
    if os.environ.get("AIGW_TEST_PG") != "1":
        pytest.skip("AIGW_TEST_PG=1 not set")
    with PostgresContainer("postgres:16-alpine", driver=None) as postgres:
        database_url = _database_url(postgres)
        _migrate(database_url)
        yield database_url


@asynccontextmanager
async def _store(database_url: str) -> AsyncIterator[TortoiseRequestCacheStore]:
    """Connect the way the app does — ``init_db`` carries ``_enable_global_fallback``.

    WHY: the store reaches the database through the implicit connection, so a test that hand-rolled
    ``Tortoise.init`` could keep passing after production wiring changed underneath it.
    """
    await close_db()
    await init_db(database_url)
    try:
        await RequestCacheEntry.all().delete()
        yield TortoiseRequestCacheStore(secret_store=LocalSecretStore(_TEST_KEY))
    finally:
        await close_db()


def _write(key_hash: str, response: dict) -> GlobalRequestCacheWrite:
    return GlobalRequestCacheWrite(
        key_hash=key_hash,
        key_version=_KEY_VERSION_V2,
        prompt_hash="p" * 64,
        provider="anthropic",
        model="anthropic/claude-haiku-4-5",
        response=response,
        response_size_bytes=128,
    )


# --- 1. create-only conflicts on a real unique constraint --------------------------------------


@pytest.mark.asyncio
async def test_concurrent_fills_leave_exactly_one_row_and_one_winner(migrated_postgres) -> None:
    """Plan §5.3 and §8.12 — genuinely concurrent, on the backend that has real concurrency."""
    key = "b" * 64
    async with _store(migrated_postgres) as store:
        first = {"id": "first", "choices": []}
        second = {"id": "second", "choices": []}

        results = await asyncio.gather(
            store.set_if_absent(_write(key, first)),
            store.set_if_absent(_write(key, second)),
        )

        assert sorted(results) == ["race_lost", "stored"]
        assert await RequestCacheEntry.filter(key_hash=key).count() == 1
        winner = first if results[0] == "stored" else second
        assert await store.get_global(key) == winner


@pytest.mark.asyncio
async def test_a_lost_race_does_not_poison_the_callers_transaction(migrated_postgres) -> None:
    """The Postgres-only hazard: a unique violation aborts its transaction.

    Falsified: with the ``in_transaction()`` block removed from ``set_if_absent``, the ``count()``
    below raises ``TransactionManagementError: current transaction is aborted, commands ignored
    until end of transaction block``, and so would every later statement the caller runs. The
    sibling test above still passes in that state — it does not run inside a caller transaction —
    so this is the only test that pins the savepoint.
    """
    key = "c" * 64
    async with _store(migrated_postgres) as store:
        async with in_transaction():
            assert await store.set_if_absent(_write(key, {"id": "winner"})) == "stored"
            assert await store.set_if_absent(_write(key, {"id": "loser"})) == "race_lost"

            # The caller's transaction is still usable — this is the whole point.
            assert await RequestCacheEntry.filter(key_hash=key).count() == 1
            assert await store.get_global(key) == {"id": "winner"}


@pytest.mark.asyncio
async def test_an_unmigrated_database_reports_not_stored_rather_than_a_lost_race() -> None:
    """A NOT NULL violation is the same exception class as a lost race, on the real backend.

    Before migration 0009 ``expires_at`` is still NOT NULL, and every v2 fill writes NULL into it by
    design — so the INSERT raises ``IntegrityError``, exactly as a unique conflict does. Mapping the
    class to ``race_lost`` reported "someone else stored it first" against a permanently empty
    table, at ``logger.debug``, in any deployment that skipped the migration.

    Falsified by deleting the confirming ``exists()``: both arms return ``race_lost``, zero rows.

    The nested arm is the Postgres-only half. The failed INSERT aborted its transaction, so the
    confirming read is only possible because it runs AFTER the ``async with`` exited and the
    savepoint rolled back — inside the block it would raise ``TransactionManagementError`` and take
    the caller's unrelated work down with it.
    """
    if os.environ.get("AIGW_TEST_PG") != "1":
        pytest.skip("AIGW_TEST_PG=1 not set")
    key = "d" * 64
    with PostgresContainer("postgres:16-alpine", driver=None) as postgres:
        database_url = _database_url(postgres)
        _migrate(database_url, "models", "0008_widen_account_username")

        async with _store(database_url) as store:
            assert await store.set_if_absent(_write(key, {"id": "never-lands"})) == "not_stored"
            assert await RequestCacheEntry.filter(key_hash=key).count() == 0

            async with in_transaction():
                assert await store.set_if_absent(_write(key, {"id": "nor-this"})) == "not_stored"
                # The caller's transaction is still usable after the classification.
                assert await RequestCacheEntry.filter(key_hash=key).count() == 0


# --- 2. the nullable-expiry migration on Postgres ----------------------------------------------


@pytest.mark.asyncio
async def test_0009_drops_not_null_on_a_populated_database_without_touching_indexes() -> None:
    """Plan §4.2 steps 3–5 on the dialect that takes the declarative path.

    Postgres needs no table rebuild, so migration 0009's index restoration is deliberately a no-op
    here. That makes the index set a falsifiable claim: if the Postgres path ever started rebuilding
    the table, these two snapshots would differ.
    """
    if os.environ.get("AIGW_TEST_PG") != "1":
        pytest.skip("AIGW_TEST_PG=1 not set")
    with PostgresContainer("postgres:16-alpine", driver=None) as postgres:
        database_url = _database_url(postgres)
        _migrate(database_url, "models", "0008_widen_account_username")

        ciphertext = await LocalSecretStore(_TEST_KEY).encrypt(json.dumps(_V1_RESPONSE))
        expires_at = datetime.now(UTC) + timedelta(hours=6)
        conn = await asyncpg.connect(database_url)
        try:
            assert await conn.fetchval(
                "select attnotnull from pg_attribute where attrelid = $1::regclass"
                " and attname = 'expires_at'",
                _TABLE,
            ), "the premise: 0008 declares expires_at NOT NULL"

            await conn.execute(
                f"insert into {_TABLE} (id, key_hash, key_version, account_id, profile_name,"
                " prompt_hash, provider, model, response_ciphertext, response_size_bytes,"
                " created_at, updated_at, expires_at, last_hit_at, hit_count)"
                " values ($1, $2, 'aigw-chat-cache-v1', 'acct-1', 'default', $3, 'anthropic',"
                " 'anthropic/claude-haiku-4-5', $4, $5, now(), now(), $6, now(), 7)",
                uuid.uuid4(),
                _V1_KEY_HASH,
                "p" * 64,
                ciphertext,
                len(ciphertext),
                expires_at,
            )
            indexes_before = {
                row["indexname"]: row["indexdef"]
                for row in await conn.fetch(
                    "select indexname, indexdef from pg_indexes where tablename = $1", _TABLE
                )
            }
            assert len(indexes_before) >= 7, f"0008 should carry the indexes: {indexes_before}"
        finally:
            await conn.close()

        _migrate(database_url)

        conn = await asyncpg.connect(database_url)
        try:
            assert not await conn.fetchval(
                "select attnotnull from pg_attribute where attrelid = $1::regclass"
                " and attname = 'expires_at'",
                _TABLE,
            )
            indexes_after = {
                row["indexname"]: row["indexdef"]
                for row in await conn.fetch(
                    "select indexname, indexdef from pg_indexes where tablename = $1", _TABLE
                )
            }
            assert indexes_after == indexes_before

            # The v1 row is untouched, expiry included, and still decrypts.
            row = await conn.fetchrow(f"select * from {_TABLE} where key_hash = $1", _V1_KEY_HASH)
            assert row is not None
            assert row["expires_at"] == expires_at
            assert row["hit_count"] == 7
            assert (
                json.loads(await LocalSecretStore(_TEST_KEY).decrypt(row["response_ciphertext"]))
                == _V1_RESPONSE
            )

            # ...and the column now accepts the indefinite global write.
            await conn.execute(
                f"insert into {_TABLE} (id, key_hash, key_version, account_id, profile_name,"
                " prompt_hash, provider, model, response_ciphertext, response_size_bytes,"
                " created_at, updated_at, expires_at, hit_count)"
                f" values ($1, $2, '{_KEY_VERSION_V2}', '{GLOBAL_SENTINEL}', '{GLOBAL_SENTINEL}',"
                " $3, 'openrouter', 'openrouter/x', 'v1:x:y', 8, now(), now(), NULL, 0)",
                uuid.uuid4(),
                "d" * 64,
                "q" * 64,
            )
            assert (
                await conn.fetchval(
                    f"select expires_at from {_TABLE} where key_hash = $1", "d" * 64
                )
                is None
            )
        finally:
            await conn.close()

        assert "No migrations to apply" in _migrate(database_url).stdout


# --- 3. atomic hit metadata under real concurrency ---------------------------------------------


@pytest.mark.asyncio
async def test_every_concurrent_hit_is_counted(migrated_postgres) -> None:
    """Plan §8.13 — twenty simultaneous hits on one shared row must count twenty.

    Falsified: swapping the ``F()`` increment for load / ``+= 1`` / ``save()`` records **3** of the
    20 hits here. The identical break passes on SQLite, which serializes writers — so this test,
    not the unit test, is what holds the increment to being computed by the database.
    """
    key = "e" * 64
    hits = 20
    async with _store(migrated_postgres) as store:
        assert await store.set_if_absent(_write(key, {"id": "shared", "choices": []})) == "stored"

        responses = await asyncio.gather(*(store.get_global(key) for _ in range(hits)))

        assert all(response == {"id": "shared", "choices": []} for response in responses)
        row = await RequestCacheEntry.get(key_hash=key)
        assert row.hit_count == hits
        assert row.last_hit_at is not None
