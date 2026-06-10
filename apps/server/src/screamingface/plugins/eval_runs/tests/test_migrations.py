"""Tests for the additive `favorite` column back-fill."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from tortoise import Tortoise

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs._migrations import ensure_favorite_column
from screamingface.plugins.eval_runs.store import EvalRunStore


@pytest.fixture
async def app_with_eval_runs(temp_state_path: Path) -> AsyncIterator[FastAPI]:
    config = AppConfig(plugins=["state", "eval-runs"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        yield app


async def _favorite_columns() -> set[str]:
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict("PRAGMA table_info('eval_run')")
    return {row["name"] for row in rows}


async def test_ensure_favorite_column_is_idempotent(app_with_eval_runs: FastAPI) -> None:
    # generate_schemas already created the column; re-running must be a no-op.
    assert "favorite" in await _favorite_columns()
    await ensure_favorite_column()
    await ensure_favorite_column()
    assert "favorite" in await _favorite_columns()


async def test_ensure_favorite_column_backfills_legacy_table(
    app_with_eval_runs: FastAPI,
) -> None:
    conn = Tortoise.get_connection("default")
    # Simulate a pre-favorite local DB by dropping the column (SQLite 3.35+).
    await conn.execute_query("ALTER TABLE eval_run DROP COLUMN favorite")
    assert "favorite" not in await _favorite_columns()

    await ensure_favorite_column()
    assert "favorite" in await _favorite_columns()

    # The back-filled column has the expected default and the store works.
    store = EvalRunStore()
    run = await store.create(spec_name="x", url4_expression="x", started_at=datetime.now(UTC))
    assert run.favorite is False
    listed = await store.list_summaries(limit=10)
    assert [r.spec_name for r in listed] == ["x"]
