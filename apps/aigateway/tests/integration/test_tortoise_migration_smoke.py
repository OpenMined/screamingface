from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import asyncpg  # type: ignore[import-untyped]
import pytest
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

pytestmark = pytest.mark.needs_postgres


@pytest.mark.skipif(os.environ.get("AIGW_TEST_PG") != "1", reason="AIGW_TEST_PG=1 not set")
def test_tortoise_migrate_creates_accounts_table() -> None:
    app_dir = Path(__file__).resolve().parents[2]
    with PostgresContainer("postgres:16-alpine", driver=None) as postgres:
        database_url = (
            f"postgres://{postgres.username}:{quote(postgres.password, safe='')}"
            f"@{postgres.get_container_host_ip()}:{postgres.get_exposed_port(5432)}"
            f"/{postgres.dbname}"
        )
        env = {**os.environ, "AIGATEWAY_DATABASE_URL": database_url}
        command = [
            sys.executable,
            "-m",
            "tortoise",
            "-c",
            "aigateway.db.TORTOISE_CONFIG",
            "migrate",
        ]
        # Replay the deployed upgrade path: stop at the previous head, insert
        # real rows, then apply the rest — ADD COLUMN defects that only fail
        # on populated tables (SF-244 audit F01) surface here, not on fresh DBs.
        subprocess.run(
            [*command, "models", "0005_secret_store"],
            cwd=app_dir,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

        async def _seed_rows() -> None:
            conn = await asyncpg.connect(database_url)
            try:
                await conn.execute(
                    "insert into accounts (id, username, password_hash, created_at, is_active)"
                    " values (gen_random_uuid(), 'u1', 'x', now(), true)"
                )
                await conn.execute(
                    "insert into oauth_connections"
                    " (id, provider, label, status, credential_locator, created_at, account_id)"
                    " select gen_random_uuid(), 'anthropic', 'work', 'active', '{}'::jsonb,"
                    " now(), id from accounts limit 1"
                )
            finally:
                await conn.close()

        asyncio.run(_seed_rows())

        subprocess.run(command, cwd=app_dir, env=env, check=True, capture_output=True, text=True)
        rerun = subprocess.run(
            command,
            cwd=app_dir,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "No migrations to apply" in rerun.stdout

        async def _tables() -> set[str]:
            conn = await asyncpg.connect(database_url)
            try:
                rows = await conn.fetch(
                    "select table_name from information_schema.tables where table_schema = 'public'"
                )
                return {row["table_name"] for row in rows}
            finally:
                await conn.close()

        assert {
            "accounts",
            "credential_blobs",
            "oauth_connections",
            "request_cache_entries",
            "secret_master_keys",
            "tortoise_migrations",
        } <= asyncio.run(_tables())

        async def _auth_type_column() -> tuple[list, Any]:
            conn = await asyncpg.connect(database_url)
            try:
                values = await conn.fetch("select auth_type from oauth_connections")
                meta = await conn.fetchrow(
                    "select is_nullable, column_default from information_schema.columns"
                    " where table_name = 'oauth_connections' and column_name = 'auth_type'"
                )
                return list(values), meta
            finally:
                await conn.close()

        values, meta = asyncio.run(_auth_type_column())
        assert [row["auth_type"] for row in values] == ["oauth"], (
            "pre-existing rows must be backfilled with the default"
        )
        assert meta is not None and meta["is_nullable"] == "NO"
        assert "oauth" in str(meta["column_default"])
