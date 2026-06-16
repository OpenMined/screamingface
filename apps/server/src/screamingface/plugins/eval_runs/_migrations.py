"""Idempotent additive schema patches for eval_runs.

The state plugin uses ``Tortoise.generate_schemas(safe=True)``, which only
creates missing *tables* — it never ALTERs an existing one. So a column added
to ``EvalRun`` after a local DB already exists (e.g. ``favorite``) must be
back-filled here. SQLite-scoped: the desktop app's local state DB is SQLite;
Postgres is a deployment concern (see ``plugins/state/README.md``).
"""

from __future__ import annotations

import logging

from tortoise import Tortoise

logger = logging.getLogger(__name__)


async def ensure_favorite_column() -> None:
    """Add ``eval_run.favorite`` to a pre-existing table that lacks it.

    Idempotent: a no-op when the column is already present (fresh installs get
    it from ``generate_schemas``) or when the table does not exist yet.
    """
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict("PRAGMA table_info('eval_run')")
    if not rows:
        return  # table not created yet — generate_schemas owns first creation
    columns = {row["name"] for row in rows}
    if "favorite" in columns:
        return
    await conn.execute_query("ALTER TABLE eval_run ADD COLUMN favorite INT NOT NULL DEFAULT 0")
    logger.info("eval_runs: added missing 'favorite' column to eval_run")
