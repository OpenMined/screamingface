"""Integration tests for eval_runs HTTP routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs.models import EvalQuestion
from screamingface.plugins.eval_runs.store import EvalRunStore


@pytest.fixture
async def async_client(temp_state_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    config = AppConfig(plugins=["state", "eval-runs"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


async def test_list_empty(async_client: httpx.AsyncClient) -> None:
    r = await async_client.get("/eval_runs")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_returns_desc_by_started_at(async_client: httpx.AsyncClient) -> None:
    store = EvalRunStore()
    base = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)
    for i in range(3):
        await store.create(
            spec_name=f"spec-{i}",
            url4_expression="x",
            started_at=base.replace(hour=10 + i),
        )

    r = await async_client.get("/eval_runs")
    assert r.status_code == 200
    body = r.json()
    assert [row["spec_name"] for row in body] == ["spec-2", "spec-1", "spec-0"]
    assert "questions" not in body[0]


async def test_get_detail_returns_questions_sorted_by_idx(
    async_client: httpx.AsyncClient,
) -> None:
    store = EvalRunStore()
    run = await store.create(
        spec_name="x",
        url4_expression="x",
        started_at=datetime.now(UTC),
    )
    for i in [2, 0, 1]:
        await EvalQuestion.create(
            run=run, idx=i, question=f"q{i}", expected=f"e{i}",
        )

    r = await async_client.get(f"/eval_runs/{run.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["spec_name"] == "x"
    assert [q["idx"] for q in body["questions"]] == [0, 1, 2]


async def test_get_detail_missing_returns_404(async_client: httpx.AsyncClient) -> None:
    r = await async_client.get(f"/eval_runs/{uuid4()}")
    assert r.status_code == 404
    assert r.json() == {"detail": "run not found"}


async def test_list_supports_limit_offset(async_client: httpx.AsyncClient) -> None:
    store = EvalRunStore()
    base = datetime(2026, 5, 13, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        await store.create(
            spec_name=f"spec-{i}",
            url4_expression="x",
            started_at=base.replace(minute=i),
        )

    r = await async_client.get("/eval_runs?limit=2&offset=1")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
