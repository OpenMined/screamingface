---
title: state plugin — generic stateful storage core for plugins
status: proposed
asana_task: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214763084594920
asana_gid: 1214763084594920
created: 2026-05-13
---

# `state` plugin — generic stateful storage core

## Goal

Land a small, opinionated core plugin (`state`) that owns Tortoise ORM
lifecycle, lets other plugins register their models, and provides a
cross-cutting `BaseModel` and a generic `BaseStore` helper. DEMO-014
(eval-run persistence) and every future stateful plugin then declare
their models against `state` instead of wiring their own ORM
bootstrap.

This ticket is **DEMO-014.0** — a prerequisite for DEMO-014. It exists
because screamingface has no structured-state convention yet, and the
first plugin to land one silently sets the convention for every plugin
that follows.

## Background

screamingface currently has no Tortoise ORM, no central sqlite, and no
DAO conventions:

- The `data_store` plugin handles blob storage (filesystem), not
  structured records.
- DEMO-014 (eval-run history) is the first plugin needing structured
  state.
- DEMO-017 (history-aware /python) and DEMO-021 (Eval Studio UI) both
  depend on DEMO-014.

If DEMO-014 ships its own Tortoise bootstrap, sqlite path, env-var
prefix, and test fixtures, the next plugin (session history, prompt
library, traces index, settings backup, …) either copies all of that
or refactors. We avoid that by landing the shared core first.

## Naming

The plugin is called `state`, not `db`. `state` describes the
responsibility — durable state for plugins — independent of the
implementation. If we later add a KV-style snapshot store or swap the
engine, `state` still fits.

## Scope

In:
- `state` plugin under `apps/server/src/screamingface/plugins/state/`.
- Tortoise ORM lifecycle (init, schema bootstrap, shutdown) wired into
  the existing screamingface plugin hook system.
- Public `register_models(app_label, modules)` API for other plugins.
- Cross-cutting `BaseModel` (abstract Tortoise model) exported by
  `state`: UUID primary key, `created_at` and `updated_at` timestamps.
- Generic `BaseStore[T: Model]` helper for simple CRUD.
- pytest fixtures (`temp_state_path`, `initialized_state`) in
  `screamingface.plugins.state.testing`.
- Settings: `SF_STATE__PATH`, `SF_STATE__ECHO`.
- README that codifies the model conventions downstream plugins must
  follow.

Out:
- Per-plugin separate sqlite files.
- Postgres driver. Model code stays Postgres-compatible; URL is
  swappable, but exercising it is a deployment concern.
- `aerich` and destructive schema migrations. Separate follow-up.
- Cross-plugin transactions or foreign keys spanning `app_label`s.

## Design

### Architecture

A single core plugin `state` owns the database lifecycle. Other
plugins depend on it (declared in `Plugin.depends`), register their
models during their own `setup()`, and either subclass `BaseStore` for
simple CRUD or use Tortoise querysets directly.

```
state (core)
├── plugin.py          StatePlugin, StateSettings, lifecycle
├── registry.py        ModelRegistry, build_config()
├── base.py            BaseModel (abstract, UUID + timestamps)
├── store.py           BaseStore[T] generic DAO helper
├── testing.py         pytest fixtures
├── README.md          conventions for downstream plugins
└── tests/
    ├── test_plugin.py
    ├── test_registry.py
    └── test_store.py
```

### Topology

One shared sqlite file at `~/.screamingface/state.db` (configurable
via `SF_STATE__PATH`). Tortoise "apps" namespace models per plugin via
the `app_label` argument — table names never collide, and a plugin can
be reasoned about in isolation.

One file makes backup and inspection trivial on desktop. We
deliberately do not split per-plugin files; it adds connection
overhead and prevents joining-related queries within a plugin's own
data without buying us anything desktop users care about.

### Registration API

```python
class StatePlugin(Plugin):
    def register_models(self, app_label: str, modules: list[str]) -> None: ...
```

Plugins call this from their own `setup()`:

```python
# eval_runs/plugin.py
class EvalRunsPlugin(Plugin):
    name = "eval-runs"
    depends = ["state"]

    def setup(self, app, hooks, classes, routes):
        state = classes.get(StatePlugin)
        state.register_models(
            "eval_runs",
            ["screamingface.plugins.eval_runs.models"],
        )
        # ... register routes, etc.
```

Errors:
- Duplicate `app_label` → `ValueError` raised synchronously.
- Calling `register_models` after Tortoise has initialized →
  `RuntimeError("state plugin already initialized; register models in setup()")`.

### Lifecycle

`state.setup()` creates an empty `ModelRegistry` and registers two
hooks on the existing screamingface plugin hook system:

1. `app.startup` →
   - Ensure parent dir for `SF_STATE__PATH` exists (`mkdir(parents=True, exist_ok=True)`).
   - Build Tortoise config from the registry, including
     `use_tz=True` and `timezone="UTC"`.
   - `await Tortoise.init(config=...)`.
   - `await Tortoise.generate_schemas(safe=True)`.
   - Set `app.state.state_ready = True`.
2. `app.shutdown` →
   - `await Tortoise.close_connections()`.

> **Why not FastAPI `lifespan`?** Tortoise enterprise patterns
> recommend the `lifespan` context manager. screamingface's existing
> plugin convention uses its own hook registry (`hooks.register("app.startup", ...)`).
> Project conventions win — using a different mechanism just for `state`
> would split the codebase.

Plugins **must not** query in `setup()` — only after startup. The
README documents this. Any work that needs the DB lives in a request
handler or another post-startup hook.

### Cross-cutting `BaseModel`

```python
# state/base.py
from tortoise import fields
from tortoise.models import Model


class BaseModel(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(primary_key=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
```

All plugin models inherit from `state.BaseModel`. Every record gets a
UUID identifier and audit timestamps for free, and downstream plugins
don't reinvent the convention.

### `BaseStore[T]`

```python
# state/store.py
from typing import Any, Generic, TypeVar
from tortoise.models import Model

T = TypeVar("T", bound=Model)


class BaseStore(Generic[T]):
    model: type[T]   # set by subclass

    async def create(self, **fields: Any) -> T: ...
    async def get(self, id: Any) -> T | None: ...
    async def list(self, *, limit: int = 50, offset: int = 0, **filters: Any) -> list[T]: ...
    async def update(self, id: Any, **fields: Any) -> T: ...
    async def delete(self, id: Any) -> bool: ...
```

Subclassing is optional. Composite or joined queries call Tortoise
directly.

### Settings

```
SF_STATE__PATH = ~/.screamingface/state.db   # default
SF_STATE__ECHO = false                       # SQL echo for debugging
```

`StateSettings(PluginSettings)` follows the existing screamingface
pattern: `env_prefix="SF_STATE__"`, `env_nested_delimiter="__"`.

### Test fixtures

```python
# state/testing.py
@pytest.fixture
def temp_state_path(tmp_path) -> Path: ...

@pytest.fixture
async def initialized_state(temp_state_path) -> AsyncIterator[FastAPI]:
    # boot a minimal FastAPI app with state activated, yield, tear down
    ...
```

Plugin test suites import these. Every test gets an isolated sqlite
file in `tmp_path`.

### Migrations

`generate_schemas(safe=True)` only. Additive-only schema, no `aerich`.

This is an explicit trade-off for the desktop context: screamingface
ships as a desktop app with bundled code, has no multi-environment
migration story, and no DB ops team. Destructive migrations (rename a
column, change a type) require shipping a one-shot patch in an app
update.

If/when screamingface grows a server-deployed component, we adopt
`aerich`. Tracked as a separate follow-up ticket.

### Model conventions (codified in README)

Downstream plugins follow these (mirroring the `tortoise-dev`
enterprise patterns):

- Models live in a `models/` subpackage, never a single `models.py`.
- One file per model.
- Each concrete model has an abstract `Base<Entity>` interface (for
  service-layer mocks and transition models during schema rewrites).
- All models inherit from `state.BaseModel` (UUID pk + timestamps).
- Class member order: `class Meta` first, then fields, then
  class/private methods, then public methods.
- `models/__init__.py` re-exports both the `Base<Entity>` and the
  concrete model.

Reviewers enforce these. The README in `plugins/state/` is the single
source of truth.

## Error handling

| Condition | Behaviour |
| --- | --- |
| Duplicate `app_label` | `ValueError` from `register_models` |
| Registration after init | `RuntimeError` from `register_models` |
| Missing parent dir for `SF_STATE__PATH` | Auto-created |
| Schema mismatch (renamed/changed column) | Surfaced by Tortoise on first query; not auto-repaired. README says: bump app version and ship a one-shot patch. |

## Testing

- **`test_registry.py`** — registration succeeds; duplicate
  `app_label` raises; `build_config()` produces expected dict with
  `use_tz=True`, `timezone="UTC"`; post-init registration raises.
- **`test_plugin.py`** — boot a FastAPI app with `state` plus an
  inline test-only plugin that declares one toy model; assert
  `state.state_ready` after startup; assert teardown closes
  connections.
- **`test_store.py`** — define a toy `BaseModel` subclass, run a
  `BaseStore` subclass through `create → get → list → update → delete`.

Hermetic: every test uses a `tmp_path`-based sqlite file. Async tests
via `pytest-asyncio`.

```
cd apps/server
uv run pytest src/screamingface/plugins/state/tests/ -v
```

Expected: 6–8 tests green, <3s.

## Acceptance criteria

- [ ] `state` plugin auto-discovered and loads.
- [ ] `register_models(app_label, modules)` callable from another
      plugin's `setup()`; duplicate `app_label` raises; post-init
      registration raises.
- [ ] On app startup, Tortoise initializes (`use_tz=True`,
      `timezone="UTC"`) with all collected registrations;
      `generate_schemas(safe=True)` runs idempotently.
- [ ] On app shutdown, Tortoise connections close cleanly.
- [ ] `SF_STATE__PATH` overrides default; parent dir auto-created.
- [ ] `state.BaseModel` exported and usable as an abstract base by
      downstream plugin models.
- [ ] `state.BaseStore[T]` exported with create/get/list/update/delete;
      round-trip exercised in `test_store.py`.
- [ ] `screamingface.plugins.state.testing` exports `temp_state_path`
      and `initialized_state` fixtures.
- [ ] Smoke test: a test-only plugin registers a model inheriting
      `state.BaseModel` and round-trips insert→read.
- [ ] README documents: registration API, conventions, depending on
      `state`, writing tests, current migration limitation.
- [ ] pyright + ruff clean.

## Dependencies

Add to `apps/server/pyproject.toml`:

```toml
"tortoise-orm>=0.21",
```

sqlite driver is bundled; no extras needed. `pytest-asyncio` is
already a test dep — verify in plan step.

## Follow-ups

- **DEMO-014** spec gets updated: drop the "sqlite + Tortoise
  bootstrap + `SF_EVAL_RUNS__DB_PATH`" section; replace with "models/
  subpackage with `Base<Entity>`, inherit `state.BaseModel`, declare
  via `state.register_models`, write DAO as `BaseStore` subclass."
- New low-priority Asana ticket: **Adopt `aerich` migrations when a
  server-deployed component lands.**
