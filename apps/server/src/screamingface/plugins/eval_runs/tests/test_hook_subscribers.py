"""Direct hook-driven persistence tests for eval-runs (SF-165).

These exercise the subscribers without driving them through /ensemble —
gives a small surface and fast feedback. Full /ensemble round-trip is
covered in test_e2e_persistence.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs._hook_payloads import (
    HOOK_QUESTION_CHECKED,
    HOOK_RUN_FAILED,
    HOOK_RUN_FINISHED,
    HOOK_RUN_STARTED,
)
from screamingface.plugins.eval_runs.models import EvalQuestion, EvalRun


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


@pytest.mark.asyncio
async def test_run_started_inserts_running_row(app_with_eval_runs: FastAPI) -> None:
    run_id = str(uuid4())
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_STARTED,
        run_id=run_id,
        spec_name="hle-claude",
        url4_expression="hello",
        started_at=datetime.now(UTC),
    )
    row = await EvalRun.get(id=run_id)
    assert row.spec_name == "hle-claude"
    assert row.status == "running"
    assert row.url4_expression == "hello"
    assert row.accuracy is None


@pytest.mark.asyncio
async def test_question_checked_inserts_eval_question_row(
    app_with_eval_runs: FastAPI,
) -> None:
    run_id = str(uuid4())
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_STARTED,
        run_id=run_id,
        spec_name="hle",
        url4_expression="x",
        started_at=datetime.now(UTC),
    )

    for i in range(3):
        await app_with_eval_runs.state.hooks.emit_async(
            HOOK_QUESTION_CHECKED,
            run_id=run_id,
            question=f"q{i}",
            expected=str(i),
            predicted=str(i),
            correct=True,
            raw_output=str(i),
            error=None,
        )

    questions = await EvalQuestion.filter(run_id=run_id).order_by("idx")
    assert [q.idx for q in questions] == [0, 1, 2]
    assert [q.question for q in questions] == ["q0", "q1", "q2"]
    assert all(q.correct for q in questions)


@pytest.mark.asyncio
async def test_run_finished_computes_accuracy_and_marks_done(
    app_with_eval_runs: FastAPI,
) -> None:
    run_id = str(uuid4())
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_STARTED,
        run_id=run_id,
        spec_name="hle",
        url4_expression="x",
        started_at=datetime.now(UTC),
    )
    for i, correct in enumerate([True, True, False, True, False]):
        await app_with_eval_runs.state.hooks.emit_async(
            HOOK_QUESTION_CHECKED,
            run_id=run_id,
            question=f"q{i}",
            expected="e",
            predicted="p",
            correct=correct,
            raw_output="r",
            error=None,
        )

    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_FINISHED,
        run_id=run_id,
        finished_at=datetime.now(UTC),
    )

    row = await EvalRun.get(id=run_id)
    assert row.status == "done"
    assert row.total_questions == 5
    assert row.correct_questions == 3
    assert row.accuracy == pytest.approx(0.6)
    assert row.finished_at is not None


@pytest.mark.asyncio
async def test_run_failed_marks_failed_with_error(app_with_eval_runs: FastAPI) -> None:
    run_id = str(uuid4())
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_STARTED,
        run_id=run_id,
        spec_name="hle",
        url4_expression="x",
        started_at=datetime.now(UTC),
    )
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_FAILED,
        run_id=run_id,
        finished_at=datetime.now(UTC),
        error="boom",
    )

    row = await EvalRun.get(id=run_id)
    assert row.status == "failed"
    assert row.error == "boom"
    assert row.finished_at is not None
