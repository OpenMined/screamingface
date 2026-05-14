from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_tortoise_sqlite_migrate_is_idempotent(tmp_path: Path) -> None:
    app_dir = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "aigateway.sqlite3"
    database_url = f"sqlite://{database_path}"
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
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute("select name from sqlite_master where type = 'table'").fetchall()
    assert {"accounts", "tortoise_migrations"} <= {row[0] for row in rows}
