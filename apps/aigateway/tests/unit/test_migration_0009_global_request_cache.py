"""Migration 0009 makes ``request_cache_entries.expires_at`` nullable (OME-305 plan §4.2).

The unit suite builds schemas with ``Tortoise.generate_schemas()``, so migration files never
execute there. This module replays the deployed upgrade path exactly as plan §4.2 prescribes:
migrate to ``0008``, seed a REAL encrypted v1 cache row with a non-NULL expiry and hit metadata,
apply ``0009``, then prove the row, its metadata, its timestamps and the table's indexes all
survived and that the column now accepts NULL.

INVARIANT (plan §4.2 step 3): the upgrade is non-destructive. SQLite cannot ``ALTER COLUMN``, so
Tortoise's SQLite editor rebuilds the table (``CREATE TABLE new__…`` / ``INSERT … SELECT`` /
``DROP`` / ``RENAME``) — and that rebuild recreates NO indexes, because indexes live in separate
``CREATE INDEX`` statements that die with the dropped table. A plain ``ops.AlterField`` therefore
silently strips all six single-column indexes and the composite one from every local database.
``test_0009_preserves_every_index_on_sqlite`` is what makes that unacceptable instead of invisible.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aigateway.core.secrets.local import LocalSecretStore

APP_DIR = Path(__file__).resolve().parents[2]

_TEST_KEY = bytes(range(32))
_V1_RESPONSE = {"id": "cmpl-v1", "choices": [{"message": {"content": "V1-ANSWER"}}]}
_V1_KEY_HASH = "a" * 64
_TABLE = "request_cache_entries"


def _migrate(database_url: str, *target: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tortoise",
            "-c",
            "aigateway.db.TORTOISE_CONFIG",
            "migrate",
            *target,
        ],
        cwd=APP_DIR,
        env={**os.environ, "AIGATEWAY_DATABASE_URL": database_url},
        check=True,
        capture_output=True,
        text=True,
    )


def _encrypt(plaintext: str) -> str:
    return asyncio.run(LocalSecretStore(_TEST_KEY).encrypt(plaintext))


def _decrypt(ciphertext: str) -> str:
    return asyncio.run(LocalSecretStore(_TEST_KEY).decrypt(ciphertext))


def _seed_v1_row(db: Path) -> dict[str, object]:
    """Insert a genuinely encrypted v1 row with a non-NULL expiry and hit metadata."""
    payload = json.dumps(_V1_RESPONSE, separators=(",", ":"), ensure_ascii=False)
    row = {
        "id": str(uuid.uuid4()),
        "key_hash": _V1_KEY_HASH,
        "key_version": "aigw-chat-cache-v1",
        "account_id": "acct-1",
        "profile_name": "default",
        "prompt_hash": "p" * 64,
        "provider": "anthropic",
        "model": "anthropic/claude-haiku-4-5",
        "response_ciphertext": _encrypt(payload),
        "response_size_bytes": len(payload),
        "created_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(sep=" "),
        "updated_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(sep=" "),
        "expires_at": (datetime.now(UTC) + timedelta(hours=6)).isoformat(sep=" "),
        "last_hit_at": (datetime.now(UTC) - timedelta(minutes=30)).isoformat(sep=" "),
        "hit_count": 7,
    }
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    with sqlite3.connect(db) as conn:
        conn.execute(
            f"insert into {_TABLE} ({columns}) values ({placeholders})", tuple(row.values())
        )
    return row


def _read_v1_row(db: Path) -> dict[str, object]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        found = conn.execute(
            f"select * from {_TABLE} where key_hash = ?", (_V1_KEY_HASH,)
        ).fetchone()
    assert found is not None, "the seeded v1 row did not survive the migration"
    return dict(found)


def _indexes(db: Path) -> dict[str, str | None]:
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "select name, sql from sqlite_master where type = 'index' and tbl_name = ?",
            (_TABLE,),
        ).fetchall()
    return {name: sql for name, sql in rows}


def _expires_at_column(db: Path) -> sqlite3.Row:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row["name"]: row for row in conn.execute(f"pragma table_info({_TABLE})")}
    return columns["expires_at"]


def _insert_v2_row(db: Path, key_hash: str) -> None:
    """A v2 write: global sentinels and NULL expiry."""
    payload = json.dumps({"id": "cmpl-v2", "choices": []}, separators=(",", ":"))
    with sqlite3.connect(db) as conn:
        conn.execute(
            f"insert into {_TABLE} (id, key_hash, key_version, account_id, profile_name,"
            " prompt_hash, provider, model, response_ciphertext, response_size_bytes,"
            " created_at, updated_at, expires_at, hit_count)"
            " values (?, ?, ?, 'global', 'global', ?, 'openrouter', 'openrouter/x', ?, ?,"
            " datetime('now'), datetime('now'), NULL, 0)",
            (
                str(uuid.uuid4()),
                key_hash,
                "aigw-global-chat-cache-v2",
                "q" * 64,
                payload,
                len(payload),
            ),
        )


@pytest.fixture
def populated_0008(tmp_path: Path) -> tuple[Path, str, dict[str, object]]:
    """A SQLite database at migration 0008 holding one real encrypted v1 cache row."""
    db = tmp_path / "populated-0008.sqlite3"
    url = f"sqlite://{db}"
    _migrate(url, "models", "0008_widen_account_username")
    return db, url, _seed_v1_row(db)


def test_expires_at_rejects_null_before_0009(
    populated_0008: tuple[Path, str, dict[str, object]],
) -> None:
    """The premise of the whole migration: at 0008 the column is NOT NULL and SQLite enforces it.

    Unlike ``VARCHAR(n)`` (which SQLite ignores, hence 0008's Postgres-only guard), NOT NULL IS
    enforced here — so 0009 must emit real DDL on both dialects, not a no-op on SQLite.
    """
    db, _url, _row = populated_0008

    assert _expires_at_column(db)["notnull"] == 1
    with pytest.raises(sqlite3.IntegrityError):
        _insert_v2_row(db, "b" * 64)


def test_0009_keeps_the_v1_row_byte_identical(
    populated_0008: tuple[Path, str, dict[str, object]],
) -> None:
    """Plan §4.2 step 3 — ciphertext, metadata, timestamps and the existing expiry survive."""
    db, url, seeded = populated_0008

    _migrate(url)

    after = _read_v1_row(db)
    for column, expected in seeded.items():
        assert after[column] == expected, f"{column} changed across migration 0009"
    # The ciphertext is not merely equal — it still decrypts to the original response.
    assert json.loads(_decrypt(str(after["response_ciphertext"]))) == _V1_RESPONSE


def test_0009_preserves_every_index_on_sqlite(
    populated_0008: tuple[Path, str, dict[str, object]],
) -> None:
    """Plan §4.2 step 3 — indexes survive.

    SQLite's ``AlterField`` path rebuilds the table and recreates no indexes, so a declarative
    migration would leave every local database doing full scans on ``key_hash`` lookups. This is the
    assertion that forces 0009 to restore them (or to avoid the rebuild).
    """
    db, url, _row = populated_0008
    before = _indexes(db)
    assert len(before) >= 7, f"0008 should already carry the cache indexes, found {sorted(before)}"

    _migrate(url)

    assert _indexes(db) == before


def test_0009_makes_expires_at_nullable_and_accepts_a_v2_write(
    populated_0008: tuple[Path, str, dict[str, object]],
) -> None:
    """Plan §4.2 step 4 — the column accepts NULL for v2, alongside the untouched v1 row."""
    db, url, _row = populated_0008

    _migrate(url)

    assert _expires_at_column(db)["notnull"] == 0
    _insert_v2_row(db, "c" * 64)
    with sqlite3.connect(db) as conn:
        expiries = dict(
            conn.execute(f"select key_hash, expires_at from {_TABLE}").fetchall()  # type: ignore[arg-type]
        )
    assert expiries["c" * 64] is None
    assert expiries[_V1_KEY_HASH] is not None


def test_0009_is_idempotent(populated_0008: tuple[Path, str, dict[str, object]]) -> None:
    """A re-run of the deployed migration Job must be a no-op, not a second table rebuild."""
    _db, url, _row = populated_0008

    _migrate(url)
    rerun = _migrate(url)

    assert "No migrations to apply" in rerun.stdout


def test_autodetector_proposes_no_request_cache_change() -> None:
    """Plan §4.2 step 6 — no RequestCacheEntry model/migration drift remains.

    An operation that runs DDL without moving the PROJECTED state leaves Tortoise believing
    ``expires_at`` is still NOT NULL while the model declares it nullable. ``makemigrations`` would
    then propose that same AlterField again, and on SQLite applying it rebuilds the table a second
    time — dropping the indexes this migration went out of its way to keep.

    Runs out of process because the autodetector needs its own ``Tortoise.init`` and the unit suite
    shares one global registry.
    """
    script = """
import asyncio, json
from tortoise import Tortoise
from tortoise.migrations.autodetector import MigrationAutodetector
from aigateway.db import build_tortoise_config

async def main():
    config = build_tortoise_config("sqlite://:memory:")
    await Tortoise.init(config=config, init_connections=False)
    try:
        writers = await MigrationAutodetector(Tortoise.apps, config["apps"]).changes()
        print(json.dumps([op.describe() for w in writers for op in w.operations]))
    finally:
        await Tortoise.close_connections()

asyncio.run(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=APP_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    proposed = json.loads(result.stdout.strip().splitlines()[-1])

    cache_ops = [op for op in proposed if "RequestCacheEntry" in op]
    assert cache_ops == [], (
        f"autodetector proposes {cache_ops} — migration 0009 does not move the projected state, so "
        "a future `makemigrations` would re-alter the column and rebuild the table again"
    )
