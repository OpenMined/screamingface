"""Migrations must apply to a POPULATED database (SF-244 audit F01/F04).

The unit suite builds schemas via Tortoise.generate_schemas(), so migration
files never execute there — and a fresh-DB migrate also cannot catch
ADD COLUMN defects that only fail when rows already exist (e.g. a NOT NULL
column without a SQL DEFAULT). This test replays the deployed upgrade path:
migrate to the previous head, insert real rows, then apply the rest.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

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
