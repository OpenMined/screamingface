---
title: eval_runs plugin — benchmark run persistence
status: proposed
asana_task: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214568118252060
asana_gid: 1214568118252060
sf_id: SF-160
depends_on: SF-197 (state plugin)
blocks: DEMO-017 (history-aware /python), DEMO-021 (Eval Studio UI)
created: 2026-05-13
---

# `eval_runs` plugin — benchmark run persistence

## Goal

Persist eval/benchmark runs and their per-question results so the Eval
Studio UI (DEMO-021) can show a history of runs, and so the orchestrator
(DEMO-017) can append questions as they're evaluated.

This is a **thin plugin** sitting on top of the `state` core (SF-197):
declare two Tortoise models, expose two HTTP read endpoints, and offer
a small DAO surface. No ORM lifecycle, no schema bootstrap, no settings
beyond what state already provides — all of that is delegated.

## Background

`state` (DEMO-014.0, merged) owns Tortoise initialization, sqlite at
`~/.screamingface/state.db`, and the cross-cutting `BaseModel` (UUID pk +
timestamps). It also enforces conventions: models in a `models/`
subpackage, one file per model, every concrete model has an abstract
`Base<Entity>` interface, and member ordering.

Before `state` existed, the original DEMO-014 spec described its own
sqlite file, its own `Tortoise.init`, its own `SF_EVAL_RUNS__DB_PATH`,
and hand-written `CREATE TABLE` SQL. All of that is gone — this spec
sits on top of `state` and only describes what's specific to eval runs.

## Scope

In:
- New plugin `apps/server/src/screamingface/plugins/eval_runs/`.
- Two Tortoise models: `EvalRun` and `EvalQuestion` (with their abstract
  `Base*` siblings).
- Pydantic response DTOs.
- `EvalRunStore` extending `state.BaseStore[EvalRun]` for simple CRUD,
  with a couple of plugin-specific methods that need joins / prefetch.
- HTTP routes:
  - `GET /eval_runs?limit=50&offset=0` — list runs without their
    questions.
  - `GET /eval_runs/{run_id}` — full run with questions, 404 on miss.
- Plugin wiring via `depends = ["state"]` and
  `state.register_models("eval_runs", [...])` in `setup()`.
- Tests: unit-level model invariants, store round-trip, route
  integration.

Out:
- `GET /eval_runs/{run_id}/stream` (SSE) — deferred to a follow-up
  ticket if/when live updates are needed.
- The benchmark runner that *creates* runs — that's DEMO-017.
- Auth/authz on these endpoints — local desktop, no multi-tenant story.

## Design

### File layout (mirrors state README conventions)

```
plugins/eval_runs/
├── __init__.py
├── plugin.py             EvalRunsPlugin (depends=["state"])
├── models/
│   ├── __init__.py       re-exports Base + concrete
│   ├── eval_run.py       BaseEvalRun + EvalRun
│   └── eval_question.py  BaseEvalQuestion + EvalQuestion
├── schemas.py            Pydantic DTOs for HTTP responses
├── store.py              EvalRunStore(BaseStore[EvalRun])
├── routes.py             create_router() → APIRouter
└── tests/
    ├── __init__.py
    ├── conftest.py       imports state fixtures
    ├── test_models.py
    ├── test_store.py
    └── test_routes.py
```

### Models

Both concrete models inherit from `state.BaseModel`, so they get
`id: UUID`, `created_at`, `updated_at` for free.

**`EvalRun`** — one row per benchmark run.

```python
# models/eval_run.py
from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel

RunStatus = ("running", "done", "failed")  # CharEnumField below


class BaseEvalRun(BaseModel):
    class Meta:
        abstract = True

    spec_name = fields.CharField(max_length=128)        # e.g. "hle-claude"
    url4_expression = fields.TextField()
    started_at = fields.DatetimeField()
    finished_at = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=16, default="running")  # running|done|failed
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

**`EvalQuestion`** — one row per question evaluated within a run.

```python
# models/eval_question.py
from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel


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

> **Schema deltas vs. the original DEMO-014 spec.** Composite PK
> `(run_id, idx)` becomes UUID pk + unique constraint on `(run, idx)` —
> preserves the "one answer per (run, idx)" invariant while keeping the
> state-convention UUID. Started/finished timestamps become
> `DatetimeField`. `created_at`/`updated_at` come for free from
> `state.BaseModel`. Cascade delete is on the FK declaration.

### Pydantic schemas (`schemas.py`)

```python
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

### Store (`store.py`)

```python
from __future__ import annotations

from uuid import UUID

from screamingface.plugins.state.store import BaseStore
from screamingface.plugins.eval_runs.models import EvalRun


class EvalRunStore(BaseStore[EvalRun]):
    model = EvalRun

    async def list_summaries(self, *, limit: int = 50, offset: int = 0) -> list[EvalRun]:
        """List runs (no questions) ordered by started_at DESC."""
        return await EvalRun.all().order_by("-started_at").offset(offset).limit(limit)

    async def get_with_questions(self, run_id: UUID) -> EvalRun | None:
        return (
            await EvalRun.filter(id=run_id)
            .prefetch_related("questions")
            .first()
        )
```

All other CRUD (`create`, `get`, `update`, `delete`) comes from
`BaseStore`. `EvalQuestion` rows are created via `await EvalQuestion.create(run=run, ...)` directly from DEMO-017 — no DAO wrapper.

### Routes (`routes.py`)

```python
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

    @router.get("/eval_runs", response_model=list[EvalRunSummaryOut])
    async def list_runs(request: Request, limit: int = 50, offset: int = 0):
        store = request.app.state.eval_run_store
        runs = await store.list_summaries(limit=limit, offset=offset)
        return [EvalRunSummaryOut.model_validate(r) for r in runs]

    @router.get("/eval_runs/{run_id}", response_model=EvalRunOut)
    async def get_run(request: Request, run_id: UUID):
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

### Plugin (`plugin.py`)

```python
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

### Lifecycle

1. `state.setup()` runs (state declared in `depends`).
2. `eval_runs.setup()` runs: registers its models with state, attaches
   `EvalRunStore` to `app.state.eval_run_store`, registers routes.
3. App startup hook fires: state initializes Tortoise + generates
   schemas. The `eval_run` and `eval_question` tables are created
   idempotently.
4. Request handlers reach the store via `request.app.state.eval_run_store`.
5. App shutdown: state closes connections.

`EvalRunStore` is stateless; one instance per app is fine.

## Error Handling

| Condition | Behaviour |
| --- | --- |
| `GET /eval_runs/{run_id}` with unknown id | 404 with `{"detail": "run not found"}` |
| Schema mismatch from prior version | Surfaced by Tortoise on first query — manual patch required (per state README) |
| `EvalQuestion` insert with duplicate `(run, idx)` | IntegrityError → bubbles up; not retried |
| List with `limit < 0` or `offset < 0` | FastAPI/Pydantic validation rejects with 422 |

## Testing

- **`test_models.py`** — invariants only (no DB): `EvalRun` and
  `EvalQuestion` are `state.BaseModel` subclasses; `EvalQuestion.Meta`
  declares `unique_together = (("run", "idx"),)`; FK has
  `on_delete=fields.CASCADE`; ordering on EvalRun is `-started_at`.
- **`test_store.py`** — integration with state lifecycle: create a run +
  3 questions, `list_summaries` returns DESC-ordered, `get_with_questions`
  returns prefetched questions, cascade delete removes child rows,
  status transitions (running → done with accuracy).
- **`test_routes.py`** — integration via `TestClient`: list endpoint
  shape, detail endpoint 200 + 404, questions sorted by `idx` in detail
  response.

All tests use the `temp_state_path` fixture from `state.testing`. Boot a
FastAPI app with `plugins=["state", "eval-runs"]`.

```
cd apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/ -v
```

Expected: 10–14 tests green, <3s.

## Acceptance Criteria

- [ ] Plugin auto-discovers and loads when listed in `AppConfig.plugins`.
- [ ] On startup, `eval_run` and `eval_question` tables are created
      idempotently (via state's `generate_schemas(safe=True)`).
- [ ] `EvalRunStore` exposes inherited CRUD (`create`, `get`, `list`,
      `update`, `delete`) plus `list_summaries(limit, offset)` and
      `get_with_questions(run_id)`.
- [ ] `GET /eval_runs?limit=50&offset=0` returns runs ordered by
      `started_at` DESC, excluding questions.
- [ ] `GET /eval_runs/{run_id}` returns the run with questions sorted by
      `idx`; 404 on unknown id.
- [ ] Cascade delete: deleting a run also removes its questions
      (verified via store test).
- [ ] Duplicate `(run, idx)` pair raises an integrity error.
- [ ] pyright + ruff clean.

## Out of Scope (deferred)

- `GET /eval_runs/{run_id}/stream` (SSE) for live updates.
- Filtering/pagination beyond `limit`+`offset` (e.g. by `spec_name` or
  `status`) — easy to add when a consumer needs it.
- `DELETE /eval_runs/{run_id}` HTTP endpoint — store supports it, but
  no UI need yet.
- The benchmark runner that *creates* runs (DEMO-017).

## Follow-ups

- DEMO-017 wires `/python` execution to insert into `EvalRun` /
  `EvalQuestion` as it runs.
- If live updates are needed, DEMO-014.1 adds the SSE stream endpoint.
