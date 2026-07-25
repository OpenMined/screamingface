"""Migration 0010 must produce real DDL and destroy no data (OME-590).

Companion to `test_migration_populated_db` (whose `_migrate` helper is reused
rather than duplicated); kept in its own module so the append-only test rule
holds. Both exist because the unit suite builds schemas with
`Tortoise.generate_schemas()`, which never executes a migration file — so a
migration can be wrong in ways the rest of the suite is structurally blind to.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .test_migration_populated_db import _migrate


def test_0010_creates_real_indexes_and_preserves_rows(tmp_path: Path) -> None:
    """Two Tortoise operations look like they emit DDL and do not.

    `AlterModelOptions` is state-only (its `database_forward` returns None), so
    it would register `unique_together` with no constraint in the database; and
    `AddField(db_index=True)` updates state without a `CREATE INDEX`. Either one
    leaves generate_schemas-built test databases correct and every *migrated*
    database wrong — so assert against `sqlite_master` directly.

    OME-591's concurrent JIT provisioning depends on the unique constraint being
    real: without it, two simultaneous first requests from one user silently
    create two accounts instead of raising IntegrityError.
    """
    db = tmp_path / "external_identity.sqlite3"
    url = f"sqlite://{db}"

    _migrate(url, "models", "0009_global_credential_pools")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "insert into accounts (id, username, password_hash, created_at, is_active)"
            " values ('a1', 'legacy-local-user', 'hashed', datetime('now'), 1)"
        )

    _migrate(url)

    with sqlite3.connect(db) as conn:
        indexes = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where tbl_name='accounts' and type='index'"
            )
        }
        columns = {row[1]: row for row in conn.execute("pragma table_info(accounts)")}
        preserved = conn.execute(
            "select password_hash from accounts where username = 'legacy-local-user'"
        ).fetchone()[0]

    assert "uid_accounts_external_identity" in indexes
    assert "idx_accounts_email" in indexes
    assert columns["password_hash"][3] == 0, "password_hash must become NULLable"
    assert preserved == "hashed", "widening to NULL must not disturb existing local accounts"


def test_0010_does_not_cascade_delete_dependent_rows(tmp_path: Path) -> None:
    """INVARIANT: no migration may destroy user data.

    SQLite cannot alter a column's nullability, so Tortoise rebuilds the table:
    CREATE new / INSERT SELECT / **DROP TABLE accounts** / RENAME. That DROP
    carries no FK guard, so under the default `PRAGMA foreign_keys=ON` it fires
    ON DELETE CASCADE across every child row — `oauth_connections` and
    `global_credential_pools` are silently emptied by a migration that reports
    OK. 0010 therefore runs non-atomically with the pragma disabled around the
    rebuild.

    Asserted on `global_credential_pools` specifically: the sibling test covers
    oauth_connections, and this is the newer FK most likely to be forgotten.
    """
    db = tmp_path / "cascade.sqlite3"
    url = f"sqlite://{db}"

    _migrate(url, "models", "0009_global_credential_pools")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "insert into accounts (id, username, password_hash, created_at, is_active)"
            " values ('a1', 'pool-admin', 'hashed', datetime('now'), 1)"
        )
        conn.execute(
            "insert into global_credential_pools"
            " (id, provider, label, auth_type, is_active, created_at, updated_at, created_by_id)"
            " values ('p1', 'anthropic', 'default', 'api_key', 1,"
            " datetime('now'), datetime('now'), 'a1')"
        )

    _migrate(url)

    with sqlite3.connect(db) as conn:
        pools = conn.execute("select id, created_by_id from global_credential_pools").fetchall()
        accounts = conn.execute("select count(*) from accounts").fetchone()[0]

    assert pools == [("p1", "a1")], "the accounts rebuild must not cascade-delete child rows"
    assert accounts == 1
