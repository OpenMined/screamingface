"""SF-270: a finished run is 'degraded' (not 'done') when rows were collected
as errors (e.g. a model backend was unavailable), and 'done' when none were.

Mirrors the async lifespan fixture pattern in test_hook_subscribers.py so
Tortoise is initialized on the test's own event loop (a sync TestClient would
init on a different loop and deadlock on cross-loop DB access)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs._hook_payloads import (
    HOOK_RUN_FINISHED,
    HOOK_RUN_STARTED,
)
from screamingface.plugins.eval_runs.models import EvalRun


@pytest.fixture
def temp_state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "state.db"
    monkeypatch.setenv("SF_STATE__PATH", str(db))
    return db


@pytest.fixture
async def app_with_eval_runs(temp_state_path: Path):
    config = AppConfig(plugins=["state", "eval-runs"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        yield app


async def _start(app: FastAPI, run_id: str, spec: str = "ScoredLiveTruth") -> None:
    await app.state.hooks.emit_async(
        HOOK_RUN_STARTED,
        run_id=run_id,
        spec_name=spec,
        url4_expression="(...)",
        started_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_finished_with_collected_errors_is_degraded(app_with_eval_runs: FastAPI) -> None:
    run_id = str(uuid4())
    await _start(app_with_eval_runs, run_id)
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_FINISHED,
        run_id=run_id,
        finished_at=datetime.now(UTC),
        collected_errors=5,
    )
    row = await EvalRun.get(id=run_id)
    assert row.status == "degraded"
    assert row.error and "errored" in row.error


@pytest.mark.asyncio
async def test_finished_clean_is_done(app_with_eval_runs: FastAPI) -> None:
    run_id = str(uuid4())
    await _start(app_with_eval_runs, run_id)
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_FINISHED,
        run_id=run_id,
        finished_at=datetime.now(UTC),
        collected_errors=0,
    )
    row = await EvalRun.get(id=run_id)
    assert row.status == "done"
    assert row.error is None
