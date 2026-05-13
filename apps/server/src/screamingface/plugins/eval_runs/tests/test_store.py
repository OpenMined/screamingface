"""Integration tests for EvalRunStore — uses a real Tortoise connection
via the state plugin's lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs.models import EvalQuestion
from screamingface.plugins.eval_runs.store import EvalRunStore


@pytest.fixture
async def app_with_eval_runs(temp_state_path: Path) -> AsyncIterator[FastAPI]:
    config = AppConfig(plugins=["state", "eval-runs"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        yield app


async def test_store_create_get_roundtrip(app_with_eval_runs: FastAPI) -> None:
    store = EvalRunStore()
    started = datetime.now(UTC)
    run = await store.create(
        spec_name="hle-claude",
        url4_expression="/claude()!hello",
        started_at=started,
    )
    fetched = await store.get(run.id)
    assert fetched is not None
    assert fetched.spec_name == "hle-claude"
    assert fetched.status == "running"


async def test_list_summaries_orders_by_started_at_desc(
    app_with_eval_runs: FastAPI,
) -> None:
    store = EvalRunStore()
    base = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)
    for i in range(3):
        await store.create(
            spec_name=f"spec-{i}",
            url4_expression="x",
            started_at=base.replace(hour=10 + i),
        )

    listed = await store.list_summaries(limit=10)
    assert [r.spec_name for r in listed] == ["spec-2", "spec-1", "spec-0"]


async def test_get_with_questions_prefetches(app_with_eval_runs: FastAPI) -> None:
    store = EvalRunStore()
    run = await store.create(
        spec_name="x",
        url4_expression="x",
        started_at=datetime.now(UTC),
    )
    for i in range(3):
        await EvalQuestion.create(
            run=run,
            idx=i,
            question=f"q{i}",
            expected=f"e{i}",
        )

    fetched = await store.get_with_questions(run.id)
    assert fetched is not None
    assert len(fetched.questions) == 3
    assert sorted(q.idx for q in fetched.questions) == [0, 1, 2]


async def test_get_with_questions_missing_returns_none(
    app_with_eval_runs: FastAPI,
) -> None:
    from uuid import uuid4

    store = EvalRunStore()
    assert await store.get_with_questions(uuid4()) is None


async def test_cascade_delete_removes_questions(app_with_eval_runs: FastAPI) -> None:
    store = EvalRunStore()
    run = await store.create(
        spec_name="x",
        url4_expression="x",
        started_at=datetime.now(UTC),
    )
    await EvalQuestion.create(run=run, idx=0, question="q", expected="e")
    assert await EvalQuestion.all().count() == 1

    deleted = await store.delete(run.id)
    assert deleted is True
    assert await EvalQuestion.all().count() == 0


async def test_duplicate_run_idx_raises(app_with_eval_runs: FastAPI) -> None:
    from tortoise.exceptions import IntegrityError

    store = EvalRunStore()
    run = await store.create(
        spec_name="x",
        url4_expression="x",
        started_at=datetime.now(UTC),
    )
    await EvalQuestion.create(run=run, idx=0, question="q1", expected="e1")
    with pytest.raises(IntegrityError):
        await EvalQuestion.create(run=run, idx=0, question="q2", expected="e2")


async def test_status_transition(app_with_eval_runs: FastAPI) -> None:
    store = EvalRunStore()
    run = await store.create(
        spec_name="x",
        url4_expression="x",
        started_at=datetime.now(UTC),
    )
    assert run.status == "running"
    updated = await store.update(
        run.id,
        status="done",
        accuracy=0.75,
        total_questions=4,
        correct_questions=3,
    )
    assert updated.status == "done"
    assert updated.accuracy == 0.75
