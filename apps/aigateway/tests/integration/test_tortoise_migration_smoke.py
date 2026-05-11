from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
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

        assert {"accounts", "tortoise_migrations"} <= asyncio.run(_tables())
