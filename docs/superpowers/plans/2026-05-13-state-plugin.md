# `state` plugin — Implementation Plan (SF-197 / DEMO-014.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a `state` core plugin that owns Tortoise ORM lifecycle, lets other plugins register their models, exports a cross-cutting `BaseModel` and a generic `BaseStore[T]` helper, and provides pytest fixtures.

**Architecture:** A new plugin under `apps/server/src/screamingface/plugins/state/`. The plugin attaches itself to `app.state.state_plugin` in `setup()` and registers `app.startup`/`app.shutdown` hook callbacks that drive `Tortoise.init` / `Tortoise.close_connections`. A small `ModelRegistry` collects per-plugin model module paths during plugin-setup phase and builds the Tortoise config when the startup hook fires. Settings via `PluginSettings`/`SF_STATE__*`. Schema bootstrap via `generate_schemas(safe=True)` (no aerich on desktop).

**Tech Stack:** Python 3.12, FastAPI, Tortoise ORM 0.21+, pydantic-settings, pytest, pytest-asyncio, uv.

**Spec:** `docs/superpowers/specs/2026-05-13-state-plugin-design.md`
**Asana:** https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214763084594920

---

## File Structure

**Create:**

- `apps/server/src/screamingface/plugins/state/__init__.py` — re-exports `StatePlugin`, `StateSettings`, `BaseModel`, `BaseStore`.
- `apps/server/src/screamingface/plugins/state/base.py` — abstract `BaseModel` (UUID pk + timestamps).
- `apps/server/src/screamingface/plugins/state/registry.py` — `ModelRegistry`: collects `{app_label: [module_paths]}`, builds Tortoise config dict.
- `apps/server/src/screamingface/plugins/state/store.py` — generic `BaseStore[T]` DAO helper.
- `apps/server/src/screamingface/plugins/state/plugin.py` — `StatePlugin`, `StateSettings`, lifecycle wiring.
- `apps/server/src/screamingface/plugins/state/testing.py` — pytest fixtures (`temp_state_path`, `initialized_state`).
- `apps/server/src/screamingface/plugins/state/README.md` — conventions for downstream plugins.
- `apps/server/src/screamingface/plugins/state/tests/__init__.py` — empty.
- `apps/server/src/screamingface/plugins/state/tests/fixtures/__init__.py` — empty, marks fixtures as a package.
- `apps/server/src/screamingface/plugins/state/tests/fixtures/toy_models.py` — toy `ToyItem` model used by integration & store tests.
- `apps/server/src/screamingface/plugins/state/tests/test_registry.py`
- `apps/server/src/screamingface/plugins/state/tests/test_base.py`
- `apps/server/src/screamingface/plugins/state/tests/test_store.py`
- `apps/server/src/screamingface/plugins/state/tests/test_plugin.py`

**Modify:**

- `apps/server/pyproject.toml` — add `tortoise-orm>=0.21` to `[project].dependencies`; add `pytest-asyncio>=0.23` to `[dependency-groups].dev`; add `asyncio_mode = "auto"` under `[tool.pytest.ini_options]`.

---

## Task 1: Add dependencies

**Files:**

- Modify: `apps/server/pyproject.toml`

- [ ] **Step 1: Add `tortoise-orm` to runtime deps**

In `apps/server/pyproject.toml`, the `[project].dependencies` list currently ends with `"curl_cffi>=0.15",`. Add one line:

```toml
[project]
dependencies = [
    "fastapi>=0.115",
    "httpx>=0.28",
    "uvicorn[standard]>=0.34",
    "typer>=0.15",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "mitmproxy>=12.2.2",
    "TatSu>=5.12",
    "curl_cffi>=0.15",
    "tortoise-orm>=0.21",
]
```

- [ ] **Step 2: Add `pytest-asyncio` to dev group**

Inside `[dependency-groups].dev`, add `"pytest-asyncio>=0.23",` alongside the existing `pytest` entries.

- [ ] **Step 3: Enable pytest-asyncio auto mode**

In the existing `[tool.pytest.ini_options]` block, add a single line so all async tests are picked up without per-test markers:

```toml
[tool.pytest.ini_options]
testpaths = ["tests", "src/screamingface/plugins"]
asyncio_mode = "auto"
markers = [
    "e2e: end-to-end test using subprocess server",
    "e2e_live: e2e test requiring real Anthropic API key",
]
```

- [ ] **Step 4: Sync deps**

Run:

```bash
cd apps/server
uv sync
```

Expected: lock updates, both new packages install without errors.

- [ ] **Step 5: Verify Tortoise import works**

```bash
cd apps/server
uv run python -c "from tortoise import Tortoise, fields; from tortoise.models import Model; print(Tortoise.__module__)"
```

Expected output: `tortoise`

- [ ] **Step 6: Commit**

```bash
git add apps/server/pyproject.toml apps/server/uv.lock
git commit -m "build(SF-197): add tortoise-orm and pytest-asyncio deps"
```

---

## Task 2: Cross-cutting `BaseModel`

**Files:**

- Create: `apps/server/src/screamingface/plugins/state/__init__.py`
- Create: `apps/server/src/screamingface/plugins/state/base.py`
- Create: `apps/server/src/screamingface/plugins/state/tests/__init__.py`
- Create: `apps/server/src/screamingface/plugins/state/tests/test_base.py`

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
mkdir -p apps/server/src/screamingface/plugins/state/tests
: > apps/server/src/screamingface/plugins/state/__init__.py
: > apps/server/src/screamingface/plugins/state/tests/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `apps/server/src/screamingface/plugins/state/tests/test_base.py`:

```python
"""Tests for the cross-cutting BaseModel."""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model

from screamingface.plugins.state.base import BaseModel


def test_basemodel_is_abstract() -> None:
    assert BaseModel._meta.abstract is True


def test_basemodel_has_uuid_primary_key() -> None:
    pk = BaseModel._meta.fields_map["id"]
    assert isinstance(pk, fields.UUIDField)
    assert pk.pk is True


def test_basemodel_has_audit_timestamps() -> None:
    fmap = BaseModel._meta.fields_map
    assert isinstance(fmap["created_at"], fields.DatetimeField)
    assert isinstance(fmap["updated_at"], fields.DatetimeField)
    assert fmap["created_at"].auto_now_add is True
    assert fmap["updated_at"].auto_now is True


def test_basemodel_is_a_tortoise_model() -> None:
    assert issubclass(BaseModel, Model)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/state/tests/test_base.py -v
```

Expected: `ImportError` / `ModuleNotFoundError` for `screamingface.plugins.state.base`.

- [ ] **Step 4: Write minimal implementation**

Create `apps/server/src/screamingface/plugins/state/base.py`:

```python
"""Cross-cutting abstract BaseModel for every state-plugin-managed table.

Every downstream plugin model inherits from this. Gives every record a UUID
primary key and audit timestamps (`created_at`, `updated_at`) for free.
"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class BaseModel(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(pk=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
```

- [ ] **Step 5: Re-export from package `__init__.py`**

Set `apps/server/src/screamingface/plugins/state/__init__.py` to:

```python
"""state plugin — generic stateful storage core for plugins."""

from __future__ import annotations

from screamingface.plugins.state.base import BaseModel

__all__ = ["BaseModel"]
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/state/tests/test_base.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add apps/server/src/screamingface/plugins/state/__init__.py \
        apps/server/src/screamingface/plugins/state/base.py \
        apps/server/src/screamingface/plugins/state/tests/__init__.py \
        apps/server/src/screamingface/plugins/state/tests/test_base.py
git commit -m "feat(SF-197): add state.BaseModel (UUID pk + timestamps)"
```

---

## Task 3: `ModelRegistry`

**Files:**

- Create: `apps/server/src/screamingface/plugins/state/registry.py`
- Create: `apps/server/src/screamingface/plugins/state/tests/test_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/server/src/screamingface/plugins/state/tests/test_registry.py`:

```python
"""Tests for ModelRegistry."""

from __future__ import annotations

import pytest

from screamingface.plugins.state.registry import ModelRegistry


def test_register_then_build_config() -> None:
    reg = ModelRegistry()
    reg.register("eval_runs", ["screamingface.plugins.eval_runs.models"])
    cfg = reg.build_config(db_url="sqlite:///:memory:")
    assert cfg["connections"]["default"] == "sqlite:///:memory:"
    assert cfg["apps"]["eval_runs"] == {
        "models": ["screamingface.plugins.eval_runs.models"],
        "default_connection": "default",
    }
    assert cfg["use_tz"] is True
    assert cfg["timezone"] == "UTC"


def test_register_multiple_app_labels() -> None:
    reg = ModelRegistry()
    reg.register("eval_runs", ["screamingface.plugins.eval_runs.models"])
    reg.register("sessions", ["screamingface.plugins.sessions.models"])
    cfg = reg.build_config(db_url="sqlite:///:memory:")
    assert set(cfg["apps"].keys()) == {"eval_runs", "sessions"}


def test_register_duplicate_app_label_raises() -> None:
    reg = ModelRegistry()
    reg.register("eval_runs", ["a"])
    with pytest.raises(ValueError, match="already registered"):
        reg.register("eval_runs", ["b"])


def test_register_empty_modules_raises() -> None:
    reg = ModelRegistry()
    with pytest.raises(ValueError, match="at least one module"):
        reg.register("eval_runs", [])


def test_register_after_init_raises() -> None:
    reg = ModelRegistry()
    reg.register("eval_runs", ["a"])
    reg.mark_initialized()
    with pytest.raises(RuntimeError, match="already initialized"):
        reg.register("sessions", ["b"])


def test_is_empty_flag() -> None:
    reg = ModelRegistry()
    assert reg.is_empty is True
    reg.register("eval_runs", ["a"])
    assert reg.is_empty is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/state/tests/test_registry.py -v
```

Expected: `ModuleNotFoundError` for `screamingface.plugins.state.registry`.

- [ ] **Step 3: Write minimal implementation**

Create `apps/server/src/screamingface/plugins/state/registry.py`:

```python
"""ModelRegistry — collects per-plugin model module paths and builds the Tortoise config.

Other plugins call StatePlugin.register_models() during their own setup() phase.
The collected entries are turned into a Tortoise config dict on startup, when the
state plugin's app.startup hook fires.
"""

from __future__ import annotations

from typing import Any


class ModelRegistry:
    def __init__(self) -> None:
        self._apps: dict[str, list[str]] = {}
        self._initialized: bool = False

    @property
    def is_empty(self) -> bool:
        return not self._apps

    def register(self, app_label: str, modules: list[str]) -> None:
        if self._initialized:
            raise RuntimeError(
                "state plugin already initialized; register models in setup() before app.startup"
            )
        if not modules:
            raise ValueError("at least one module must be provided")
        if app_label in self._apps:
            raise ValueError(f"app_label {app_label!r} is already registered")
        self._apps[app_label] = list(modules)

    def mark_initialized(self) -> None:
        self._initialized = True

    def build_config(self, *, db_url: str) -> dict[str, Any]:
        return {
            "connections": {"default": db_url},
            "apps": {
                label: {"models": list(mods), "default_connection": "default"}
                for label, mods in self._apps.items()
            },
            "use_tz": True,
            "timezone": "UTC",
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/state/tests/test_registry.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/screamingface/plugins/state/registry.py \
        apps/server/src/screamingface/plugins/state/tests/test_registry.py
git commit -m "feat(SF-197): add ModelRegistry for state plugin"
```

---

## Task 4: `BaseStore[T]`

**Files:**

- Create: `apps/server/src/screamingface/plugins/state/store.py`
- Modify: `apps/server/src/screamingface/plugins/state/__init__.py`

> Tests for `BaseStore` need a live Tortoise connection, so they're written in Task 6 (integration tests) once the toy model + fixtures are in place. This task ships the implementation only.

- [ ] **Step 1: Write `BaseStore`**

Create `apps/server/src/screamingface/plugins/state/store.py`:

```python
"""Generic CRUD helper for plugins that don't need composite queries.

Plugins subclass BaseStore by setting `model`:

    class EvalRunStore(BaseStore[EvalRun]):
        model = EvalRun

then call store.create(...), store.get(...), etc. Composite queries (joins,
aggregates) should use Tortoise's queryset API directly — BaseStore is not the
place for them.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from tortoise.exceptions import DoesNotExist
from tortoise.models import Model

T = TypeVar("T", bound=Model)


class BaseStore(Generic[T]):
    model: type[T]

    def __init__(self, model: type[T] | None = None) -> None:
        if model is not None:
            self.model = model
        if not hasattr(self, "model"):
            raise TypeError(
                f"{type(self).__name__} must set `model` as a class attribute "
                "or pass it to __init__"
            )

    async def create(self, **fields: Any) -> T:
        return await self.model.create(**fields)

    async def get(self, id: Any) -> T | None:
        try:
            return await self.model.get(id=id)
        except DoesNotExist:
            return None

    async def list(self, *, limit: int = 50, offset: int = 0, **filters: Any) -> list[T]:
        qs = self.model.filter(**filters) if filters else self.model.all()
        return await qs.offset(offset).limit(limit)

    async def update(self, id: Any, **fields: Any) -> T:
        obj = await self.model.get(id=id)
        for key, value in fields.items():
            setattr(obj, key, value)
        await obj.save(update_fields=list(fields.keys()))
        return obj

    async def delete(self, id: Any) -> bool:
        deleted = await self.model.filter(id=id).delete()
        return deleted > 0
```

- [ ] **Step 2: Re-export from package `__init__.py`**

Update `apps/server/src/screamingface/plugins/state/__init__.py` to:

```python
"""state plugin — generic stateful storage core for plugins."""

from __future__ import annotations

from screamingface.plugins.state.base import BaseModel
from screamingface.plugins.state.store import BaseStore

__all__ = ["BaseModel", "BaseStore"]
```

- [ ] **Step 3: Sanity-check the import**

```bash
cd apps/server
uv run python -c "from screamingface.plugins.state import BaseModel, BaseStore; print(BaseModel, BaseStore)"
```

Expected: prints both class reprs, no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/server/src/screamingface/plugins/state/store.py \
        apps/server/src/screamingface/plugins/state/__init__.py
git commit -m "feat(SF-197): add BaseStore[T] generic CRUD helper"
```

---

## Task 5: `StatePlugin` + `StateSettings` + lifecycle

**Files:**

- Create: `apps/server/src/screamingface/plugins/state/plugin.py`
- Modify: `apps/server/src/screamingface/plugins/state/__init__.py`

> Plugin lifecycle is exercised by the integration test in Task 7. This task ships the class + settings; the no-DB unit-level invariants we can check now go in test_plugin.py.

- [ ] **Step 1: Write the failing test (unit-level, no DB)**

Create `apps/server/src/screamingface/plugins/state/tests/test_plugin.py`:

```python
"""Unit tests for StatePlugin / StateSettings (no DB yet)."""

from __future__ import annotations

from pathlib import Path

from screamingface.plugins.state.plugin import StatePlugin, StateSettings


def test_settings_defaults(monkeypatch) -> None:
    # Strip any host-env overrides
    monkeypatch.delenv("SF_STATE__PATH", raising=False)
    monkeypatch.delenv("SF_STATE__ECHO", raising=False)
    s = StateSettings()
    assert s.path == Path.home() / ".screamingface" / "state.db"
    assert s.echo is False


def test_settings_env_override(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "x.db"
    monkeypatch.setenv("SF_STATE__PATH", str(target))
    monkeypatch.setenv("SF_STATE__ECHO", "true")
    s = StateSettings()
    assert s.path == target
    assert s.echo is True


def test_plugin_class_attrs() -> None:
    assert StatePlugin.name == "state"
    assert StatePlugin.settings_class is StateSettings
    assert StatePlugin.depends == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/state/tests/test_plugin.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `apps/server/src/screamingface/plugins/state/plugin.py`:

```python
"""StatePlugin — Tortoise ORM lifecycle and model-registration entrypoint.

Other plugins:
  1. Declare `depends = ["state"]` so this plugin's setup() runs first.
  2. In their own setup(), retrieve the StatePlugin instance from
     `app.state.state_plugin` and call .register_models(app_label, modules).
  3. Make sure they do NOT query the DB during setup() — only on/after the
     `app.startup` hook fires.

state itself emits app.startup/app.shutdown callbacks that drive
Tortoise.init / generate_schemas(safe=True) / close_connections.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict
from tortoise import Tortoise

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.state.registry import ModelRegistry

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class StateSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_STATE__",
        env_nested_delimiter="__",
        extra="ignore",
    )

    path: Path = Path.home() / ".screamingface" / "state.db"
    echo: bool = False


class StatePlugin(Plugin):
    name = "state"
    description = "Generic stateful storage core — Tortoise ORM + sqlite"
    tags: list[str] = ["product:system"]
    depends: list[str] = []
    settings_class = StateSettings

    def __init__(self) -> None:
        self.registry = ModelRegistry()

    def register_models(self, app_label: str, modules: list[str]) -> None:
        """Public API: declare a plugin's Tortoise models.

        Call from another plugin's setup(). Raises after the state plugin has
        initialized Tortoise (i.e. after the app.startup hook has fired).
        """
        self.registry.register(app_label, modules)

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        # Expose this instance to other plugins so they can call register_models()
        # from their own setup(). Mirrors the data-store plugin's app.state.blob_store.
        app.state.state_plugin = self
        assert isinstance(self.settings, StateSettings)  # set by registry.activate
        settings = self.settings

        async def _on_startup() -> None:
            settings.path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite://{settings.path}"
            config = self.registry.build_config(db_url=db_url)
            if self.registry.is_empty:
                logger.info("state plugin: no models registered, skipping Tortoise.init")
                return
            await Tortoise.init(config=config)
            await Tortoise.generate_schemas(safe=True)
            self.registry.mark_initialized()
            app.state.state_ready = True
            logger.info("state plugin: Tortoise initialized at %s", settings.path)

        async def _on_shutdown() -> None:
            if getattr(app.state, "state_ready", False):
                await Tortoise.close_connections()
                app.state.state_ready = False
                logger.info("state plugin: Tortoise connections closed")

        hooks.register("app.startup", _on_startup, plugin_name=self.name, priority=10)
        hooks.register("app.shutdown", _on_shutdown, plugin_name=self.name, priority=200)
```

- [ ] **Step 4: Re-export from package `__init__.py`**

Update `apps/server/src/screamingface/plugins/state/__init__.py`:

```python
"""state plugin — generic stateful storage core for plugins."""

from __future__ import annotations

from screamingface.plugins.state.base import BaseModel
from screamingface.plugins.state.plugin import StatePlugin, StateSettings
from screamingface.plugins.state.store import BaseStore

__all__ = ["BaseModel", "BaseStore", "StatePlugin", "StateSettings"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/state/tests/test_plugin.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Verify plugin is auto-discovered**

```bash
cd apps/server
uv run python -c "
from screamingface.core.registry import PluginRegistry
r = PluginRegistry()
r.discover()
print('state' in {p.name for p in r.plugin_classes()})
"
```

If `plugin_classes()` is not the right method name on `PluginRegistry`, inspect the class first: `uv run python -c "from screamingface.core.registry import PluginRegistry; print(dir(PluginRegistry))"`. The check is just confirming `state` shows up after discovery — adapt to whatever inspection API the registry exposes. Expected outcome: `state` is in the discovered set.

- [ ] **Step 7: Commit**

```bash
git add apps/server/src/screamingface/plugins/state/plugin.py \
        apps/server/src/screamingface/plugins/state/__init__.py \
        apps/server/src/screamingface/plugins/state/tests/test_plugin.py
git commit -m "feat(SF-197): add StatePlugin with Tortoise lifecycle hooks"
```

---

## Task 6: Test fixtures + toy model

**Files:**

- Create: `apps/server/src/screamingface/plugins/state/testing.py`
- Create: `apps/server/src/screamingface/plugins/state/tests/fixtures/__init__.py`
- Create: `apps/server/src/screamingface/plugins/state/tests/fixtures/toy_models.py`

- [ ] **Step 1: Create the toy model module**

The toy model has to live at an importable dotted path so Tortoise can pick it up via the registry. Tests use it directly; the integration test in Task 7 registers it.

```bash
mkdir -p apps/server/src/screamingface/plugins/state/tests/fixtures
: > apps/server/src/screamingface/plugins/state/tests/fixtures/__init__.py
```

Create `apps/server/src/screamingface/plugins/state/tests/fixtures/toy_models.py`:

```python
"""A throwaway model used by state plugin tests.

Not registered by the state plugin itself — tests register it dynamically via
state.register_models("toy", ["...toy_models"]).
"""

from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel


class ToyItem(BaseModel):
    class Meta:
        table = "toy_item"

    name = fields.CharField(max_length=64)
    weight = fields.IntField(default=0)
```

- [ ] **Step 2: Write the fixtures module**

Create `apps/server/src/screamingface/plugins/state/testing.py`:

```python
"""Pytest fixtures plugins can import for their own tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig


@pytest.fixture
def temp_state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point SF_STATE__PATH at a fresh sqlite file under tmp_path."""
    db = tmp_path / "state.db"
    monkeypatch.setenv("SF_STATE__PATH", str(db))
    return db


@pytest.fixture
async def initialized_state(temp_state_path: Path) -> AsyncIterator[FastAPI]:
    """Boot a minimal FastAPI app with the state plugin active.

    Yields the app *after* the startup hook has run (Tortoise initialized),
    and runs the shutdown hook on teardown.
    """
    config = AppConfig(plugins=["state"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        yield app
```

- [ ] **Step 3: Sanity-check imports**

```bash
cd apps/server
uv run python -c "
from screamingface.plugins.state.testing import temp_state_path, initialized_state
from screamingface.plugins.state.tests.fixtures.toy_models import ToyItem
print(ToyItem)
"
```

Expected: prints `<class 'screamingface.plugins.state.tests.fixtures.toy_models.ToyItem'>`.

- [ ] **Step 4: Commit**

```bash
git add apps/server/src/screamingface/plugins/state/testing.py \
        apps/server/src/screamingface/plugins/state/tests/fixtures/__init__.py \
        apps/server/src/screamingface/plugins/state/tests/fixtures/toy_models.py
git commit -m "test(SF-197): add state.testing fixtures and ToyItem"
```

---

## Task 7: Integration test — plugin lifecycle + `BaseStore` round-trip

**Files:**

- Create: `apps/server/src/screamingface/plugins/state/tests/test_store.py`
- Modify: `apps/server/src/screamingface/plugins/state/tests/test_plugin.py` (add lifecycle integration test)

This exercises the full path: boot app → register toy model → Tortoise initializes → schema generated → `BaseStore` round-trip → shutdown closes connections.

- [ ] **Step 1: Write the failing integration tests**

Append to `apps/server/src/screamingface/plugins/state/tests/test_plugin.py`:

```python
# --- Integration tests below ---

import pytest
from pathlib import Path
from tortoise import Tortoise
from fastapi import FastAPI

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.state.plugin import StatePlugin
from screamingface.plugins.state.tests.fixtures.toy_models import ToyItem


@pytest.fixture
async def app_with_toy(temp_state_path: Path):
    """Boot an app with the state plugin and register the toy model in-test."""
    config = AppConfig(plugins=["state"], plugin_config={})
    app = create_app(config)

    # Reach the StatePlugin instance attached to app.state during setup()
    # (StatePlugin.setup sets app.state.state_plugin = self).
    state: StatePlugin = app.state.state_plugin
    state.register_models(
        "toy",
        ["screamingface.plugins.state.tests.fixtures.toy_models"],
    )

    async with app.router.lifespan_context(app):
        yield app


async def test_startup_initializes_tortoise(app_with_toy: FastAPI) -> None:
    assert app_with_toy.state.state_ready is True
    # ToyItem table exists — a query against an unknown table would raise.
    count = await ToyItem.all().count()
    assert count == 0


async def test_baseStore_roundtrip(app_with_toy: FastAPI) -> None:
    from screamingface.plugins.state.store import BaseStore

    store: BaseStore[ToyItem] = BaseStore(ToyItem)
    created = await store.create(name="alpha", weight=3)
    assert created.id is not None
    assert created.name == "alpha"

    fetched = await store.get(created.id)
    assert fetched is not None
    assert fetched.name == "alpha"
    assert fetched.weight == 3

    listed = await store.list(limit=10)
    assert len(listed) == 1

    updated = await store.update(created.id, weight=99)
    assert updated.weight == 99

    deleted = await store.delete(created.id)
    assert deleted is True
    assert await store.get(created.id) is None


async def test_get_missing_returns_none(app_with_toy: FastAPI) -> None:
    from uuid import uuid4

    from screamingface.plugins.state.store import BaseStore

    store: BaseStore[ToyItem] = BaseStore(ToyItem)
    assert await store.get(uuid4()) is None


async def test_register_after_init_raises(app_with_toy: FastAPI) -> None:
    state: StatePlugin = app_with_toy.state.state_plugin
    with pytest.raises(RuntimeError, match="already initialized"):
        state.register_models("late", ["x"])


async def test_generate_schemas_is_idempotent(temp_state_path: Path) -> None:
    """Booting twice against the same DB file must not error."""
    config = AppConfig(plugins=["state"], plugin_config={})

    for _ in range(2):
        app = create_app(config)
        state: StatePlugin = app.state.state_plugin
        state.register_models(
            "toy",
            ["screamingface.plugins.state.tests.fixtures.toy_models"],
        )
        async with app.router.lifespan_context(app):
            assert app.state.state_ready is True
```

Also create a tiny `apps/server/src/screamingface/plugins/state/tests/test_store.py` that just smoke-imports the helper (to keep `test_store.py` present as an acceptance-criterion file):

```python
"""Smoke import test for BaseStore — full behaviour is exercised in test_plugin.py."""

from __future__ import annotations

from screamingface.plugins.state.store import BaseStore


def test_basestore_requires_model() -> None:
    import pytest

    class _Bad(BaseStore):
        pass

    with pytest.raises(TypeError, match="must set `model`"):
        _Bad()
```

- [ ] **Step 2: Make pytest pick up the `temp_state_path` fixture**

The integration tests above use `temp_state_path` (defined in `testing.py`). Pytest discovers fixtures from `conftest.py`, not arbitrary modules. Create `apps/server/src/screamingface/plugins/state/tests/conftest.py`:

```python
"""Re-export state testing fixtures so they're available to tests in this dir."""

from screamingface.plugins.state.testing import (  # noqa: F401
    initialized_state,
    temp_state_path,
)
```

- [ ] **Step 3: Run all state tests to verify they pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/state/tests/ -v
```

Expected: all tests green. Total ~13 tests, runtime <5s.

If `AppConfig(plugins=["state"], plugin_config={})` fails because the registry's plugin-config dict shape differs, inspect `AppConfig` and adapt — the data_store plugin tests use the same shape, so it should work.

- [ ] **Step 4: Commit**

```bash
git add apps/server/src/screamingface/plugins/state/tests/test_plugin.py \
        apps/server/src/screamingface/plugins/state/tests/test_store.py \
        apps/server/src/screamingface/plugins/state/tests/conftest.py
git commit -m "test(SF-197): integration tests for state plugin lifecycle + BaseStore"
```

---

## Task 8: README — conventions for downstream plugins

**Files:**

- Create: `apps/server/src/screamingface/plugins/state/README.md`

- [ ] **Step 1: Write the README**

Create `apps/server/src/screamingface/plugins/state/README.md`:

````markdown
# `state` plugin

Generic stateful storage core for screamingface plugins. Owns Tortoise ORM
lifecycle, accepts model registrations from other plugins, exposes a
cross-cutting `BaseModel` and a generic `BaseStore[T]` helper, and ships
pytest fixtures.

## Quickstart for a new stateful plugin

```python
# apps/server/src/screamingface/plugins/my_plugin/plugin.py
from screamingface.plugin import Plugin
from screamingface.plugins.state.plugin import StatePlugin


class MyPlugin(Plugin):
    name = "my-plugin"
    depends = ["state"]

    def setup(self, app, hooks, classes, routes):
        state: StatePlugin = app.state.state_plugin
        state.register_models(
            "my_plugin",
            ["screamingface.plugins.my_plugin.models"],
        )
        # ... routes, etc.
```

The state plugin's `app.startup` hook runs *after* every plugin's `setup()`,
so by the time Tortoise initializes, every plugin has had its chance to
register. **Do not query the DB in `setup()`** — only in request handlers
or in your own post-startup hook.

## Model conventions (required)

Downstream plugins MUST follow these. Reviewers enforce them.

1. **Models live in a `models/` subpackage.** Never a single `models.py`.
2. **One file per model.**
3. **Each concrete model has an abstract `Base<Entity>` interface.** The
   `Base<Entity>` declares fields and pure helpers; the concrete model adds
   relations, `Meta.table`, and DB-dependent behaviour. The service layer
   accepts `Base<Entity>` so it can be unit-tested with a mock.
4. **All concrete models inherit from `state.BaseModel`** (UUID pk + `created_at` + `updated_at`).
5. **Class member order** inside any model:
   1. `class Meta` first
   2. fields
   3. class/private methods (`__str__`, `_helper`, …)
   4. public methods
6. **`models/__init__.py` re-exports both** the `Base<Entity>` and the concrete model.

### Example

```python
# my_plugin/models/widget.py
from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel


class BaseWidget(BaseModel):
    class Meta:
        abstract = True

    name = fields.CharField(max_length=128)
    weight = fields.IntField(default=0)

    def __str__(self) -> str:
        return self.name


class Widget(BaseWidget):
    class Meta:
        table = "widget"
```

```python
# my_plugin/models/__init__.py
from .widget import BaseWidget, Widget

__all__ = ["BaseWidget", "Widget"]
```

## `BaseStore[T]`

Optional CRUD helper for plugins that don't need joined or aggregate
queries:

```python
from screamingface.plugins.state.store import BaseStore
from screamingface.plugins.my_plugin.models import Widget


class WidgetStore(BaseStore[Widget]):
    model = Widget

store = WidgetStore()
w = await store.create(name="alpha", weight=3)
w = await store.get(w.id)
await store.update(w.id, weight=99)
await store.delete(w.id)
```

Composite/joined queries: skip `BaseStore`, use the queryset API
(`Widget.filter(...).prefetch_related(...)`).

## Settings

| Env var | Default | Purpose |
| --- | --- | --- |
| `SF_STATE__PATH` | `~/.screamingface/state.db` | sqlite file location |
| `SF_STATE__ECHO` | `false` | SQL echo (reserved; not yet wired) |

The parent directory is auto-created on startup.

## Testing

Import the fixtures in your plugin's `tests/conftest.py`:

```python
from screamingface.plugins.state.testing import (  # noqa: F401
    initialized_state,
    temp_state_path,
)
```

Then in your tests:

```python
import pytest


async def test_widget_create(temp_state_path):
    config = AppConfig(plugins=["state", "my-plugin"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        # query the DB here
        ...
```

Every test gets an isolated sqlite file under `tmp_path`.

## Migration limitation

The state plugin uses `Tortoise.generate_schemas(safe=True)` — additive-only.
No `aerich`. Destructive migrations (renamed columns, type changes) require
shipping a one-shot patch in an app update.

If screamingface grows a server-deployed component, we adopt aerich. Tracked
as a follow-up ticket.

## Out of scope

- Per-plugin separate database files
- Postgres driver (model code stays Postgres-compatible; URL swap is a
  deployment concern)
- aerich / destructive migrations
- Cross-plugin transactions or FKs spanning `app_label`s
````

- [ ] **Step 2: Commit**

```bash
git add apps/server/src/screamingface/plugins/state/README.md
git commit -m "docs(SF-197): add state plugin README with conventions"
```

---

## Task 9: Lint, type-check, full plugin test pass

**Files:** none (verification only)

- [ ] **Step 1: ruff**

```bash
cd apps/server
uv run ruff check src/screamingface/plugins/state
```

Expected: no issues. Fix any reported issues inline before continuing.

- [ ] **Step 2: pyright**

```bash
cd apps/server
uv run pyright src/screamingface/plugins/state
```

Expected: 0 errors. If `self.settings` typing complains in `plugin.py`, the existing assertion (`assert isinstance(self.settings, StateSettings)`) should narrow it; add a `cast` only if necessary.

- [ ] **Step 3: Full state plugin test suite**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/state/ -v
```

Expected: all tests pass. Total runtime <5s.

- [ ] **Step 4: Wider regression check**

```bash
cd apps/server
uv run pytest -q
```

Expected: no new failures vs. baseline `main`. The state plugin is opt-in and is not in any other plugin's default config, so existing tests should be unaffected.

- [ ] **Step 5: Commit anything from lint/type fixups** (only if there were any)

```bash
git add -u apps/server/src/screamingface/plugins/state
git commit -m "chore(SF-197): lint and type-check cleanups"
```

(Skip if the working tree is clean after Step 4.)

---

## Final acceptance check (from the spec)

Walk through the acceptance criteria from the spec and tick each one:

- [ ] `state` plugin auto-discovered and loads — verified in Task 5 Step 6 and via the integration test in Task 7.
- [ ] `register_models(app_label, modules)` callable from another plugin's `setup()`; duplicate `app_label` raises; post-init registration raises — Tasks 3 and 7.
- [ ] On app startup, Tortoise initializes (`use_tz=True`, `timezone="UTC"`) with all registrations; `generate_schemas(safe=True)` runs idempotently — Task 3 (config) + Task 7 (`test_generate_schemas_is_idempotent`).
- [ ] On app shutdown, Tortoise connections close cleanly — Task 5 lifecycle + Task 7 lifespan teardown exercises it.
- [ ] `SF_STATE__PATH` overrides default; parent dir auto-created — Task 5 settings test + Task 5 `mkdir(parents=True, exist_ok=True)`.
- [ ] `state.BaseModel` exported — Task 2 + `__init__.py` updates.
- [ ] `state.BaseStore[T]` exported with CRUD; round-trip exercised — Tasks 4 + 7.
- [ ] `screamingface.plugins.state.testing` exports `temp_state_path` and `initialized_state` — Task 6.
- [ ] Smoke test: toy model registered, round-tripped — Task 7.
- [ ] README documents conventions — Task 8.
- [ ] pyright + ruff clean — Task 9.

---

## Notes for the implementer

- The screamingface plugin discovery system imports every plugin's `plugin.py` automatically. As long as your file is at `plugins/state/plugin.py` and exports a class subclassing `Plugin` with a non-empty `name`, it's picked up.
- `hooks.emit_async("app.startup")` is called with no kwargs (see `core/app.py:52`). Use a closure to capture `app`.
- Settings: `plugin.settings` is auto-instantiated by `PluginRegistry.activate()` from `settings_class` (see `core/registry.py:101-110`). Don't instantiate `StateSettings()` yourself inside `setup()`.
- If pytest can't find the toy model module (`ImportError` at `Tortoise.init` time), it's almost always a missing `__init__.py` along the path — verify `tests/__init__.py` and `tests/fixtures/__init__.py` both exist.
- If the integration test hangs at startup, you probably forgot `app.state.state_plugin = self` (other plugins reach back via this) or your `app.startup` hook is awaiting something that never resolves.
