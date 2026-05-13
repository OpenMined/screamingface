# `eval_runs` plugin — Implementation Plan (SF-160 / DEMO-014)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a thin `eval_runs` plugin sitting on top of the `state` core (SF-197). Two Tortoise models (`EvalRun`, `EvalQuestion`) with abstract `Base*` siblings, Pydantic response DTOs, an `EvalRunStore` extending `state.BaseStore`, two HTTP read endpoints, and full test coverage. No new lifecycle, no new settings — `state` owns all of that.

**Architecture:** New plugin under `apps/server/src/screamingface/plugins/eval_runs/`. Models declared in a `models/` subpackage (one file per model, abstract `Base<Entity>` + concrete model inheriting `state.BaseModel`). Plugin `setup()` calls `state.register_models("eval_runs", [...])` and attaches an `EvalRunStore` to `app.state.eval_run_store`. Routes read the store from `request.app.state`.

**Tech Stack:** Python 3.12, FastAPI, Tortoise ORM 0.21+, Pydantic v2, pytest, pytest-asyncio (already installed via state plugin).

**Spec:** `docs/superpowers/specs/2026-05-13-eval-runs-persistence-design.md`
**Asana:** https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214568118252060

---

## File Structure

**Create:**

- `apps/server/src/screamingface/plugins/eval_runs/__init__.py` — empty.
- `apps/server/src/screamingface/plugins/eval_runs/models/__init__.py` — re-exports `BaseEvalRun`, `EvalRun`, `BaseEvalQuestion`, `EvalQuestion`.
- `apps/server/src/screamingface/plugins/eval_runs/models/eval_run.py` — `BaseEvalRun` (abstract) + `EvalRun` (concrete).
- `apps/server/src/screamingface/plugins/eval_runs/models/eval_question.py` — `BaseEvalQuestion` (abstract) + `EvalQuestion` (concrete, FK to `EvalRun` with cascade).
- `apps/server/src/screamingface/plugins/eval_runs/schemas.py` — Pydantic DTOs: `EvalQuestionOut`, `EvalRunSummaryOut`, `EvalRunOut`.
- `apps/server/src/screamingface/plugins/eval_runs/store.py` — `EvalRunStore(BaseStore[EvalRun])`.
- `apps/server/src/screamingface/plugins/eval_runs/routes.py` — `create_router()` exposing two endpoints.
- `apps/server/src/screamingface/plugins/eval_runs/plugin.py` — `EvalRunsPlugin` (depends `["state"]`, no settings).
- `apps/server/src/screamingface/plugins/eval_runs/tests/__init__.py` — empty.
- `apps/server/src/screamingface/plugins/eval_runs/tests/conftest.py` — re-exports `temp_state_path` from `state.testing`.
- `apps/server/src/screamingface/plugins/eval_runs/tests/test_models.py` — model invariants (no DB).
- `apps/server/src/screamingface/plugins/eval_runs/tests/test_store.py` — store integration (full lifecycle).
- `apps/server/src/screamingface/plugins/eval_runs/tests/test_routes.py` — HTTP integration via TestClient.

**Modify:** none. (All deps already installed via the merged state plugin.)

---

## Task 1: Scaffold + `EvalRun` model

**Files:**

- Create: `apps/server/src/screamingface/plugins/eval_runs/__init__.py`
- Create: `apps/server/src/screamingface/plugins/eval_runs/models/__init__.py`
- Create: `apps/server/src/screamingface/plugins/eval_runs/models/eval_run.py`
- Create: `apps/server/src/screamingface/plugins/eval_runs/tests/__init__.py`
- Create: `apps/server/src/screamingface/plugins/eval_runs/tests/test_models.py`

- [ ] **Step 1: Create the package skeleton**

```bash
cd /Users/sergey/work/openmind/screamingface
mkdir -p apps/server/src/screamingface/plugins/eval_runs/models
mkdir -p apps/server/src/screamingface/plugins/eval_runs/tests
: > apps/server/src/screamingface/plugins/eval_runs/__init__.py
: > apps/server/src/screamingface/plugins/eval_runs/tests/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `apps/server/src/screamingface/plugins/eval_runs/tests/test_models.py`:

```python
"""Unit tests for EvalRun model invariants (no DB)."""

from __future__ import annotations

from tortoise import fields

from screamingface.plugins.eval_runs.models.eval_run import BaseEvalRun, EvalRun
from screamingface.plugins.state.base import BaseModel


def test_base_eval_run_is_abstract() -> None:
    assert BaseEvalRun._meta.abstract is True


def test_eval_run_inherits_state_basemodel() -> None:
    assert issubclass(EvalRun, BaseModel)


def test_eval_run_table_name() -> None:
    assert EvalRun._meta.db_table == "eval_run"


def test_eval_run_ordering_started_at_desc() -> None:
    assert EvalRun._meta.ordering == ["-started_at"]


def test_eval_run_has_expected_fields() -> None:
    fmap = EvalRun._meta.fields_map
    # Inherited from state.BaseModel
    assert "id" in fmap
    assert "created_at" in fmap
    assert "updated_at" in fmap
    # Own fields
    assert isinstance(fmap["spec_name"], fields.CharField)
    assert isinstance(fmap["url4_expression"], fields.TextField)
    assert isinstance(fmap["started_at"], fields.DatetimeField)
    assert fmap["finished_at"].null is True
    assert isinstance(fmap["status"], fields.CharField)
    assert fmap["accuracy"].null is True
    assert fmap["total_questions"].null is True
    assert fmap["correct_questions"].null is True
    assert fmap["error"].null is True
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/test_models.py -v
```

Expected: `ModuleNotFoundError` for `screamingface.plugins.eval_runs.models.eval_run`.

- [ ] **Step 4: Write the model**

Create `apps/server/src/screamingface/plugins/eval_runs/models/eval_run.py`:

```python
"""EvalRun — one row per benchmark run."""

from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel


class BaseEvalRun(BaseModel):
    class Meta:
        abstract = True

    spec_name = fields.CharField(max_length=128)
    url4_expression = fields.TextField()
    started_at = fields.DatetimeField()
    finished_at = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=16, default="running")
    accuracy = fields.FloatField(null=True)
    total_questions = fields.IntField(null=True)
    correct_questions = fields.IntField(null=True)
    error = fields.TextField(null=True)

    def __str__(self) -> str:
        return f"{self.spec_name} ({self.status})"


class EvalRun(BaseEvalRun):
    class Meta:
        table = "eval_run"
        table_description = "Eval/benchmark runs"
        ordering = ["-started_at"]
        indexes = (("started_at",), ("spec_name",))
```

- [ ] **Step 5: Write `models/__init__.py`**

Create `apps/server/src/screamingface/plugins/eval_runs/models/__init__.py`:

```python
"""eval_runs Tortoise models."""

from __future__ import annotations

from screamingface.plugins.eval_runs.models.eval_run import BaseEvalRun, EvalRun

__all__ = ["BaseEvalRun", "EvalRun"]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/test_models.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/eval_runs/__init__.py \
        apps/server/src/screamingface/plugins/eval_runs/models/__init__.py \
        apps/server/src/screamingface/plugins/eval_runs/models/eval_run.py \
        apps/server/src/screamingface/plugins/eval_runs/tests/__init__.py \
        apps/server/src/screamingface/plugins/eval_runs/tests/test_models.py
git commit -m "feat(SF-160): scaffold eval_runs plugin with EvalRun model"
```

---

## Task 2: `EvalQuestion` model with FK + unique constraint

**Files:**

- Create: `apps/server/src/screamingface/plugins/eval_runs/models/eval_question.py`
- Modify: `apps/server/src/screamingface/plugins/eval_runs/models/__init__.py` — re-export new model.
- Modify: `apps/server/src/screamingface/plugins/eval_runs/tests/test_models.py` — append tests.

- [ ] **Step 1: Append the failing tests**

Append to `apps/server/src/screamingface/plugins/eval_runs/tests/test_models.py`:

```python
from screamingface.plugins.eval_runs.models.eval_question import (
    BaseEvalQuestion,
    EvalQuestion,
)


def test_base_eval_question_is_abstract() -> None:
    assert BaseEvalQuestion._meta.abstract is True


def test_eval_question_inherits_state_basemodel() -> None:
    assert issubclass(EvalQuestion, BaseModel)


def test_eval_question_table_name() -> None:
    assert EvalQuestion._meta.db_table == "eval_question"


def test_eval_question_unique_together_run_idx() -> None:
    assert EvalQuestion._meta.unique_together == (("run", "idx"),)


def test_eval_question_fk_cascades() -> None:
    fk = EvalQuestion._meta.fields_map["run"]
    # Tortoise stores on_delete behaviour on the relation descriptor.
    # `fields.CASCADE` is a string-valued enum in Tortoise 1.x — equality with
    # the enum or its `.value` both work.
    assert str(fk.on_delete).upper().endswith("CASCADE")


def test_eval_question_has_expected_fields() -> None:
    fmap = EvalQuestion._meta.fields_map
    assert isinstance(fmap["idx"], fields.IntField)
    assert isinstance(fmap["question"], fields.TextField)
    assert isinstance(fmap["expected"], fields.TextField)
    assert fmap["predicted"].null is True
    assert fmap["correct"].null is True
    assert fmap["raw_output"].null is True
    assert fmap["error"].null is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/test_models.py -v
```

Expected: `ModuleNotFoundError` for `screamingface.plugins.eval_runs.models.eval_question`.

- [ ] **Step 3: Write the model**

Create `apps/server/src/screamingface/plugins/eval_runs/models/eval_question.py`:

```python
"""EvalQuestion — one row per question evaluated within a run."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import fields

from screamingface.plugins.state.base import BaseModel

if TYPE_CHECKING:
    from screamingface.plugins.eval_runs.models.eval_run import EvalRun


class BaseEvalQuestion(BaseModel):
    class Meta:
        abstract = True

    idx = fields.IntField()
    question = fields.TextField()
    expected = fields.TextField()
    predicted = fields.TextField(null=True)
    correct = fields.BooleanField(null=True)
    raw_output = fields.TextField(null=True)
    error = fields.TextField(null=True)


class EvalQuestion(BaseEvalQuestion):
    class Meta:
        table = "eval_question"
        unique_together = (("run", "idx"),)

    run: fields.ForeignKeyRelation[EvalRun] = fields.ForeignKeyField(
        "eval_runs.EvalRun",
        related_name="questions",
        on_delete=fields.CASCADE,
    )
```

- [ ] **Step 4: Update `models/__init__.py`**

Replace `apps/server/src/screamingface/plugins/eval_runs/models/__init__.py` with:

```python
"""eval_runs Tortoise models."""

from __future__ import annotations

from screamingface.plugins.eval_runs.models.eval_question import (
    BaseEvalQuestion,
    EvalQuestion,
)
from screamingface.plugins.eval_runs.models.eval_run import BaseEvalRun, EvalRun

__all__ = ["BaseEvalQuestion", "BaseEvalRun", "EvalQuestion", "EvalRun"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/test_models.py -v
```

Expected: 11 passed (5 from Task 1 + 6 new).

If `test_eval_question_fk_cascades` fails because the assertion against `str(fk.on_delete)` doesn't match Tortoise 1.x's representation, inspect the actual value:

```bash
uv run python -c "
from tortoise import fields
print(repr(fields.CASCADE), type(fields.CASCADE))
"
```

then adjust the assertion to compare against the actual enum value (e.g. `fk.on_delete == fields.CASCADE`). Don't loosen the test to always pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/eval_runs/models/eval_question.py \
        apps/server/src/screamingface/plugins/eval_runs/models/__init__.py \
        apps/server/src/screamingface/plugins/eval_runs/tests/test_models.py
git commit -m "feat(SF-160): add EvalQuestion model with FK cascade + unique (run, idx)"
```

---

## Task 3: Pydantic response DTOs

**Files:**

- Create: `apps/server/src/screamingface/plugins/eval_runs/schemas.py`

> No tests for schemas as a standalone task — they're exercised by route + store tests. The implementation goes in now so later tasks can import.

- [ ] **Step 1: Write the schemas**

Create `apps/server/src/screamingface/plugins/eval_runs/schemas.py`:

```python
"""Pydantic response DTOs for the eval_runs HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

RunStatus = Literal["running", "done", "failed"]


class EvalQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    idx: int
    question: str
    expected: str
    predicted: str | None = None
    correct: bool | None = None
    raw_output: str | None = None
    error: str | None = None


class EvalRunSummaryOut(BaseModel):
    """List view — no questions."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    spec_name: str
    url4_expression: str
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus = "running"
    accuracy: float | None = None
    total_questions: int | None = None
    correct_questions: int | None = None
    error: str | None = None


class EvalRunOut(EvalRunSummaryOut):
    """Detail view — includes questions."""

    questions: list[EvalQuestionOut] = []
```

- [ ] **Step 2: Sanity-check the import**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run python -c "
from screamingface.plugins.eval_runs.schemas import (
    EvalQuestionOut, EvalRunOut, EvalRunSummaryOut,
)
print(EvalQuestionOut, EvalRunOut, EvalRunSummaryOut)
"
```

Expected: prints three class reprs, no errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/eval_runs/schemas.py
git commit -m "feat(SF-160): add Pydantic DTOs for eval_runs HTTP responses"
```

---

## Task 4: `EvalRunStore` (with store tests using state fixtures)

**Files:**

- Create: `apps/server/src/screamingface/plugins/eval_runs/store.py`
- Create: `apps/server/src/screamingface/plugins/eval_runs/tests/conftest.py`
- Create: `apps/server/src/screamingface/plugins/eval_runs/tests/test_store.py`

> Store tests need a live Tortoise — they boot a FastAPI app with both `state` and `eval-runs` plugins inside a lifespan context. That requires Task 5's plugin wiring. To keep tasks bite-sized we'll do this in two parts: **this task writes the store + its tests, but the tests will fail until Task 5 wires the plugin.** That's deliberate TDD — the failing test pins the contract.

- [ ] **Step 1: Write the conftest**

Create `apps/server/src/screamingface/plugins/eval_runs/tests/conftest.py`:

```python
"""Re-export state testing fixtures for eval_runs tests."""

from screamingface.plugins.state.testing import (  # noqa: F401
    initialized_state,
    temp_state_path,
)
```

- [ ] **Step 2: Write the failing store tests**

Create `apps/server/src/screamingface/plugins/eval_runs/tests/test_store.py`:

```python
"""Integration tests for EvalRunStore — uses a real Tortoise connection
via the state plugin's lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs.models import EvalQuestion, EvalRun
from screamingface.plugins.eval_runs.store import EvalRunStore


@pytest.fixture
async def app_with_eval_runs(temp_state_path: Path) -> AsyncIterator[FastAPI]:
    config = AppConfig(plugins=["state", "eval-runs"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        yield app


async def test_store_create_get_roundtrip(app_with_eval_runs: FastAPI) -> None:
    store = EvalRunStore()
    started = datetime.now(timezone.utc)
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
    base = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)
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
        started_at=datetime.now(timezone.utc),
    )
    for i in range(3):
        await EvalQuestion.create(
            run=run, idx=i, question=f"q{i}", expected=f"e{i}",
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
        started_at=datetime.now(timezone.utc),
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
        started_at=datetime.now(timezone.utc),
    )
    await EvalQuestion.create(run=run, idx=0, question="q1", expected="e1")
    with pytest.raises(IntegrityError):
        await EvalQuestion.create(run=run, idx=0, question="q2", expected="e2")


async def test_status_transition(app_with_eval_runs: FastAPI) -> None:
    store = EvalRunStore()
    run = await store.create(
        spec_name="x",
        url4_expression="x",
        started_at=datetime.now(timezone.utc),
    )
    assert run.status == "running"
    updated = await store.update(
        run.id, status="done", accuracy=0.75, total_questions=4, correct_questions=3,
    )
    assert updated.status == "done"
    assert updated.accuracy == 0.75
```

- [ ] **Step 3: Run tests to confirm they fail (the right way)**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/test_store.py -v
```

Expected: either `ModuleNotFoundError` for `screamingface.plugins.eval_runs.store` (Step 4 fixes it) or, once Step 4 lands, plugin-activation errors because the `eval-runs` plugin doesn't exist yet (Task 5 fixes those). Both failure modes are expected at this stage.

- [ ] **Step 4: Write the store**

Create `apps/server/src/screamingface/plugins/eval_runs/store.py`:

```python
"""EvalRunStore — CRUD + eval-runs-specific queries on top of state.BaseStore."""

from __future__ import annotations

from uuid import UUID

from screamingface.plugins.eval_runs.models import EvalRun
from screamingface.plugins.state.store import BaseStore


class EvalRunStore(BaseStore[EvalRun]):
    model = EvalRun

    async def list_summaries(self, *, limit: int = 50, offset: int = 0) -> list[EvalRun]:
        """List runs ordered by started_at DESC, without prefetching questions."""
        return await EvalRun.all().order_by("-started_at").offset(offset).limit(limit)

    async def get_with_questions(self, run_id: UUID) -> EvalRun | None:
        return (
            await EvalRun.filter(id=run_id)
            .prefetch_related("questions")
            .first()
        )
```

- [ ] **Step 5: Commit (tests still fail — Task 5 finishes wiring)**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/eval_runs/store.py \
        apps/server/src/screamingface/plugins/eval_runs/tests/conftest.py \
        apps/server/src/screamingface/plugins/eval_runs/tests/test_store.py
git commit -m "feat(SF-160): add EvalRunStore + store tests (red until plugin wires)"
```

---

## Task 5: Routes

**Files:**

- Create: `apps/server/src/screamingface/plugins/eval_runs/routes.py`

> Routes tests come in Task 6 with the plugin wiring. This task ships the routes module so Task 6's plugin can import `create_router`.

- [ ] **Step 1: Write `routes.py`**

Create `apps/server/src/screamingface/plugins/eval_runs/routes.py`:

```python
"""HTTP routes for eval_runs — list and detail."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from screamingface.plugins.eval_runs.schemas import (
    EvalQuestionOut,
    EvalRunOut,
    EvalRunSummaryOut,
)

__all__ = ["create_router"]


def create_router() -> APIRouter:
    router = APIRouter(tags=["eval-runs"])

    @router.get(
        "/eval_runs",
        response_model=list[EvalRunSummaryOut],
        operation_id="eval_runs_list",
    )
    async def list_runs(
        request: Request, limit: int = 50, offset: int = 0
    ) -> list[EvalRunSummaryOut]:
        store = request.app.state.eval_run_store
        runs = await store.list_summaries(limit=limit, offset=offset)
        return [EvalRunSummaryOut.model_validate(r) for r in runs]

    @router.get(
        "/eval_runs/{run_id}",
        response_model=EvalRunOut,
        operation_id="eval_runs_get",
    )
    async def get_run(request: Request, run_id: UUID) -> EvalRunOut:
        store = request.app.state.eval_run_store
        run = await store.get_with_questions(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        questions = sorted(run.questions, key=lambda q: q.idx)
        summary = EvalRunSummaryOut.model_validate(run).model_dump()
        return EvalRunOut(
            **summary,
            questions=[EvalQuestionOut.model_validate(q) for q in questions],
        )

    return router
```

- [ ] **Step 2: Sanity-check import**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run python -c "
from screamingface.plugins.eval_runs.routes import create_router
print(create_router())
"
```

Expected: prints an `APIRouter` repr; no errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/eval_runs/routes.py
git commit -m "feat(SF-160): add eval_runs HTTP routes (list + detail)"
```

---

## Task 6: Plugin wiring + route tests

**Files:**

- Create: `apps/server/src/screamingface/plugins/eval_runs/plugin.py`
- Create: `apps/server/src/screamingface/plugins/eval_runs/tests/test_routes.py`

This is the keystone — once `plugin.py` lands, all the red tests from Task 4 will turn green and the route tests below will run cleanly.

- [ ] **Step 1: Write the failing route tests**

Create `apps/server/src/screamingface/plugins/eval_runs/tests/test_routes.py`:

```python
"""Integration tests for eval_runs HTTP routes."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs.models import EvalQuestion
from screamingface.plugins.eval_runs.store import EvalRunStore


@pytest.fixture
def client(temp_state_path: Path) -> Iterator[TestClient]:
    config = AppConfig(plugins=["state", "eval-runs"], plugin_config={})
    app = create_app(config)
    with TestClient(app) as c:
        yield c


def test_list_empty(client: TestClient) -> None:
    r = client.get("/eval_runs")
    assert r.status_code == 200
    assert r.json() == []


def test_list_returns_desc_by_started_at(client: TestClient) -> None:
    # Seed via direct store usage — TestClient context has lifespan already run,
    # so Tortoise is initialized.
    import asyncio

    async def seed() -> None:
        store = EvalRunStore()
        base = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)
        for i in range(3):
            await store.create(
                spec_name=f"spec-{i}",
                url4_expression="x",
                started_at=base.replace(hour=10 + i),
            )

    asyncio.run(seed())

    r = client.get("/eval_runs")
    assert r.status_code == 200
    body = r.json()
    assert [row["spec_name"] for row in body] == ["spec-2", "spec-1", "spec-0"]
    # Summary view: no `questions` key
    assert "questions" not in body[0]


def test_get_detail_returns_questions_sorted_by_idx(client: TestClient) -> None:
    import asyncio

    async def seed() -> str:
        store = EvalRunStore()
        run = await store.create(
            spec_name="x",
            url4_expression="x",
            started_at=datetime.now(timezone.utc),
        )
        # Insert in shuffled order to prove the sort
        for i in [2, 0, 1]:
            await EvalQuestion.create(
                run=run, idx=i, question=f"q{i}", expected=f"e{i}",
            )
        return str(run.id)

    run_id = asyncio.run(seed())

    r = client.get(f"/eval_runs/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["spec_name"] == "x"
    assert [q["idx"] for q in body["questions"]] == [0, 1, 2]


def test_get_detail_missing_returns_404(client: TestClient) -> None:
    r = client.get(f"/eval_runs/{uuid4()}")
    assert r.status_code == 404
    assert r.json() == {"detail": "run not found"}


def test_list_supports_limit_offset(client: TestClient) -> None:
    import asyncio

    async def seed() -> None:
        store = EvalRunStore()
        base = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)
        for i in range(5):
            await store.create(
                spec_name=f"spec-{i}",
                url4_expression="x",
                started_at=base.replace(minute=i),
            )

    asyncio.run(seed())

    r = client.get("/eval_runs?limit=2&offset=1")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
```

> **Note on `asyncio.run(seed())`** — `TestClient` is sync. We can't use the
> `app_with_eval_runs` async fixture from `test_store.py` here. Tortoise was
> initialized inside `TestClient`'s lifespan context, which runs an event
> loop briefly during enter. After enter, the connection is still live;
> `asyncio.run()` opens a new loop and Tortoise's connection pool is keyed
> per loop. **This may break.** If `asyncio.run(seed())` raises something
> like "Tortoise has not been initialized" or a closed-loop error,
> alternative: use the async fixture pattern and `httpx.AsyncClient` instead
> of `TestClient`. See the fallback in Step 4.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/test_routes.py -v
```

Expected: failures because `eval-runs` is not yet a known plugin (auto-discovery hasn't found it — `plugin.py` doesn't exist).

- [ ] **Step 3: Write the plugin**

Create `apps/server/src/screamingface/plugins/eval_runs/plugin.py`:

```python
"""EvalRunsPlugin — registers models with state and exposes HTTP routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin
from screamingface.plugins.eval_runs.routes import create_router
from screamingface.plugins.eval_runs.store import EvalRunStore

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class EvalRunsPlugin(Plugin):
    name = "eval-runs"
    description = "Persistence + read API for eval/benchmark runs"
    tags: list[str] = ["product:eval"]
    depends: list[str] = ["state"]
    settings_class = None

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        state = app.state.state_plugin
        state.register_models(
            "eval_runs",
            ["screamingface.plugins.eval_runs.models"],
        )

        app.state.eval_run_store = EvalRunStore()

        router = create_router()
        routes.add_router(self.name, router, prefix="")
```

- [ ] **Step 4: Run all eval_runs tests**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/ -v
```

Expected: all tests green. Total ~18 tests (11 models + 7 store + ~5 routes).

**Fallback if route tests fail with event-loop issues:** rewrite `test_routes.py` using the async-fixture pattern from `test_store.py` and `httpx.AsyncClient`:

```python
import httpx
from httpx import ASGITransport

@pytest.fixture
async def async_client(temp_state_path):
    config = AppConfig(plugins=["state", "eval-runs"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

async def test_list_empty(async_client):
    r = await async_client.get("/eval_runs")
    assert r.status_code == 200
    assert r.json() == []
```

Only fall back if the sync `TestClient` approach fails — keeping `TestClient` is the simpler path. Document any deviation in the commit message.

- [ ] **Step 5: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/eval_runs/plugin.py \
        apps/server/src/screamingface/plugins/eval_runs/tests/test_routes.py
git commit -m "feat(SF-160): wire EvalRunsPlugin + route tests"
```

---

## Task 7: Lint, type-check, full regression

**Files:** none (verification only)

- [ ] **Step 1: ruff**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run ruff check src/screamingface/plugins/eval_runs
```

Expected: no issues. Fix any inline before continuing.

- [ ] **Step 2: pyright**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pyright src/screamingface/plugins/eval_runs
```

Expected: 0 errors. If the `EvalQuestion.run` `ForeignKeyRelation["EvalRun"]` type confuses pyright with the `TYPE_CHECKING` block, leave the `TYPE_CHECKING` import as-is (it's the standard Tortoise pattern).

- [ ] **Step 3: Full eval_runs test suite**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/ -v
```

Expected: all tests green, <3s.

- [ ] **Step 4: Wider regression check**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest -q
```

Expected: no new failures vs. main. The `eval-runs` plugin is opt-in and not in any other plugin's default config; existing tests should be unaffected.

- [ ] **Step 5: Commit any lint/type fixups (skip if working tree clean)**

```bash
cd /Users/sergey/work/openmind/screamingface
git add -u apps/server/src/screamingface/plugins/eval_runs
git commit -m "chore(SF-160): lint and type-check cleanups"
```

---

## Final acceptance check (from the spec)

- [ ] Plugin auto-discovers and loads — Task 6 (`AppConfig(plugins=["state", "eval-runs"])` boots without error).
- [ ] `eval_run` and `eval_question` tables created idempotently — Task 4 (store create round-trip), implicit via state's `generate_schemas(safe=True)`.
- [ ] `EvalRunStore` CRUD + `list_summaries` + `get_with_questions` — Task 4 store tests.
- [ ] `GET /eval_runs` returns DESC-ordered runs without questions — Task 6 route tests.
- [ ] `GET /eval_runs/{run_id}` returns questions sorted by `idx`; 404 on unknown id — Task 6.
- [ ] Cascade delete removes child questions — Task 4 `test_cascade_delete_removes_questions`.
- [ ] Duplicate `(run, idx)` raises IntegrityError — Task 4 `test_duplicate_run_idx_raises`.
- [ ] pyright + ruff clean — Task 7.

---

## Notes for the implementer

- The `state` plugin's `app.startup` hook runs after every plugin's `setup()` and *only* initializes Tortoise if the registry is non-empty. As soon as `eval_runs.setup()` calls `state.register_models(...)`, the schema gets generated on startup.
- Tortoise model module path is `screamingface.plugins.eval_runs.models` (the package, not an individual file). Tortoise picks up models that are imported by `models/__init__.py` — which is why both `eval_run.py` and `eval_question.py` are re-exported.
- `EvalQuestion.run` field's relation string is `"eval_runs.EvalRun"` — the prefix is the `app_label` we registered, **not** the Python module path.
- `temp_state_path` (from `state.testing`) sets `SF_STATE__PATH` via monkeypatch and returns the path. The path is per-test, so tests are hermetic.
- The store tests in Task 4 are intentionally **red** until Task 5 lands the plugin. This is fine — TDD by design. Don't try to make them green by importing the model module directly or hand-initializing Tortoise; that defeats the purpose of testing the integration with the state plugin's lifecycle.
- `EvalQuestion` cascade test: after `store.delete(run.id)`, the row count for questions should be 0. If Tortoise doesn't honor the cascade at the ORM level (some drivers leave it to the DB), sqlite's FK enforcement must be on. The `state` plugin currently uses `sqlite://{path}` URL; if FK cascade fails to propagate, the fix is in `state` (set `PRAGMA foreign_keys = ON`), not in eval_runs. Report DONE_WITH_CONCERNS if you observe this.
- For the `EvalRunOut` detail response, `run.questions` after `prefetch_related("questions")` is a list-like queryset; `sorted(run.questions, key=lambda q: q.idx)` materializes it. This sorts in-Python on a small list — fine for now. If a run grows to thousands of questions we'd push the sort into the queryset, but that's premature.
