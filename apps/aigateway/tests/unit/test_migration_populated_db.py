"""Migrations must apply to a POPULATED database (SF-244 audit F01/F04).

The unit suite builds schemas via Tortoise.generate_schemas(), so migration
files never execute there — and a fresh-DB migrate also cannot catch
ADD COLUMN defects that only fail when rows already exist (e.g. a NOT NULL
column without a SQL DEFAULT). This test replays the deployed upgrade path:
migrate to the previous head, insert real rows, then apply the rest.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2]


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


def test_full_chain_applies_to_populated_database(tmp_path: Path) -> None:
    db = tmp_path / "populated.sqlite3"
    url = f"sqlite://{db}"

    # Deployed state before this release: everything up to the secret store.
    _migrate(url, "models", "0005_secret_store")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "insert into accounts (id, username, password_hash, created_at, is_active)"
            " values ('a1', 'u1', 'x', datetime('now'), 1)"
        )
        conn.execute(
            "insert into oauth_connections"
            " (id, provider, label, status, credential_locator, created_at, account_id)"
            " values ('c1', 'anthropic', 'work', 'active', '{}', datetime('now'), 'a1')"
        )

    # The upgrade must succeed with rows present and be idempotent.
    _migrate(url)
    rerun = _migrate(url)
    assert "No migrations to apply" in rerun.stdout

    with sqlite3.connect(db) as conn:
        rows = conn.execute("select auth_type from oauth_connections").fetchall()
        columns = {row[1]: row for row in conn.execute("pragma table_info(oauth_connections)")}
    assert rows == [("oauth",)], "existing rows must be backfilled with the default"
    auth_type_col = columns["auth_type"]
    assert auth_type_col[3] == 1, "auth_type must be NOT NULL"
    assert "oauth" in str(auth_type_col[4]), "auth_type must carry a SQL DEFAULT"


def test_pre_0005_credential_blob_keeps_null_ciphertext_version(tmp_path: Path) -> None:
    """A credential_blobs row predating the ciphertext_version column must read
    back as NULL — never "v1" — after migration 0005 applies (C13 / SF-327).

    ORMStore.read treats ciphertext_version IS NULL as genuine legacy plaintext
    and returns it unchanged; a "v1" stamp instead triggers prefix validation
    that would reject the un-prefixed legacy value. The NULL holds only because
    0005 adds the column with a Tortoise ORM-side default="v1" whose
    has_db_default() is False, so the emitted ALTER TABLE ADD COLUMN carries NO
    SQL DEFAULT and pre-existing rows stay NULL. Guard that invariant against a
    future "add a SQL default for consistency" change (contrast 0007's auth_type,
    which DOES carry a SQL DEFAULT — asserted above).
    """
    db = tmp_path / "legacy_blob.sqlite3"
    url = f"sqlite://{db}"

    # State before the secret store: credential_blobs exists (0003) but has no
    # ciphertext_version column yet.
    _migrate(url, "models", "0004_gemini_credential_locator")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "insert into credential_blobs"
            " (id, service, account, value, created_at, updated_at)"
            " values ('b1', 'legacy-svc', 'legacy-acct', 'plaintext-token',"
            " datetime('now'), datetime('now'))"
        )

    # Apply 0005 (adds ciphertext_version) and the remaining chain.
    _migrate(url)

    with sqlite3.connect(db) as conn:
        version = conn.execute(
            "select ciphertext_version from credential_blobs where id = 'b1'"
        ).fetchone()[0]
        columns = {row[1]: row for row in conn.execute("pragma table_info(credential_blobs)")}
    assert version is None, "pre-0005 rows must carry NULL ciphertext_version, not 'v1'"
    assert columns["ciphertext_version"][4] is None, (
        "ciphertext_version must NOT carry a SQL DEFAULT — the NULL legacy-plaintext"
        " fallback invariant (C13) depends on it"
    )


class _FakeCapabilities:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect


class _FakeClient:
    def __init__(self, dialect: str) -> None:
        self.capabilities = _FakeCapabilities(dialect)


class _RecordingSchemaEditor:
    """Captures the SQL a migration would run, without a database behind it."""

    def __init__(self, dialect: str) -> None:
        self.client = _FakeClient(dialect)
        self.executed: list[str] = []

    async def _run_sql(self, sql: str) -> None:
        self.executed.append(sql)


@pytest.mark.asyncio
async def test_widening_the_username_is_a_no_op_on_sqlite() -> None:
    """SQLite does not enforce VARCHAR length, and altering there would rebuild the table.

    That rebuild drops `accounts`, which cascades through `oauth_connections.account_id` and
    deletes every OAuth connection — the data loss `test_full_chain_applies_to_populated_database`
    caught. The correct SQLite behaviour is to do nothing at all.
    """
    editor = _RecordingSchemaEditor("sqlite")

    await _widen_username_operation().database_forward("models", None, None, editor)

    assert editor.executed == []


@pytest.mark.asyncio
async def test_widening_the_username_alters_the_column_on_postgres() -> None:
    """Postgres DOES enforce the length, so the DDL must actually run there.

    Without this the dialect guard could be inverted or over-broad and the migration would be a
    no-op everywhere — shipping a column too narrow for the addresses it is meant to hold.
    """
    editor = _RecordingSchemaEditor("postgres")

    await _widen_username_operation().database_forward("models", None, None, editor)

    assert len(editor.executed) == 1
    assert "VARCHAR(255)" in editor.executed[0]
    assert "accounts" in editor.executed[0]


def test_autodetector_proposes_no_account_change() -> None:
    """0008 must move the PROJECTED state too, not just the Postgres column.

    An operation that runs DDL without a `state_forward` leaves Tortoise's projected state at
    `max_length=64` while the model declares 255. `makemigrations` then proposes exactly the
    `AlterField(Account.username)` that 0008 exists to avoid — and applying THAT to a populated
    SQLite database rebuilds `accounts` and cascade-deletes every `oauth_connections` row. The trap
    is invisible in a diff, so it is pinned here: the autodetector must stay silent about Account.

    Runs out of process because the autodetector needs its own `Tortoise.init`, and the unit suite
    shares one global Tortoise registry.
    """
    proposed = _autodetected_operations()

    account_ops = [op for op in proposed if "Account" in op]
    assert account_ops == [], (
        f"autodetector proposes {account_ops} — migration 0008 no longer moves the projected "
        "state, so a future `makemigrations` would re-widen the column and drop oauth_connections"
    )
    # KNOWN, pre-existing and unrelated: the model's FK instance resolves `source_field`/`to_field`
    # during Tortoise.init while the migration-projected one does not, so this pair never converges.
    # It predates this branch. Asserted so the test fails loudly if it ever grows or disappears,
    # rather than silently masking a real new drift.
    assert proposed == ["Alter field account on OAuthConnection"]


def _autodetected_operations() -> list[str]:
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
    return json.loads(result.stdout.strip().splitlines()[-1])


def _widen_username_operation():
    """The operation migration 0008 actually declares — not a fresh one built by the test.

    Reaching through `Migration.operations` is what makes the two dialect tests also guard against
    someone swapping the guarded operation back for a plain `ops.AlterField`.
    """
    return _migration_0008().Migration.operations[0]


def _migration_0008():
    """Import the migration by path: its module name starts with a digit, so `import` cannot."""
    import importlib.util

    path = APP_DIR / "src/aigateway/migrations/0008_widen_account_username.py"
    spec = importlib.util.spec_from_file_location("migration_0008", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
