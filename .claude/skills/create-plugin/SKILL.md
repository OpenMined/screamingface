---
description: Scaffold a new ScreamingFace server plugin with routes, hooks, settings, and tests
user_invocable: true
---

# Create ScreamingFace Plugin

When invoked, ask the user for:
1. **Plugin type** — built-in (inside this repo) or external (standalone package)
2. **Plugin name** (kebab-case, e.g. `eval-runner`)
3. **Description** (one sentence)
4. **What it needs** — any combination of: routes, hooks, settings, class extensions, dependencies on other plugins, system deps
5. If it needs settings, ask what settings fields (name, type, default)
6. If it needs routes, ask what endpoints (method, path, brief purpose)

---

# Option A: Built-in Plugin (inside this repo)

Then generate the following files. Use the exact patterns below — they match the existing codebase conventions.

## File: `apps/server/src/screamingface/plugins/{snake_name}/__init__.py`

Empty file.

## File: `apps/server/src/screamingface/plugins/{snake_name}/plugin.py`

```python
"""<Description> plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin

if TYPE_CHECKING:
    from fastapi import FastAPI
    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class <ClassName>Plugin(Plugin):
    name = "<kebab-name>"
    # version is inherited from screamingface.__version__ for built-in plugins
    description = "<Description>"

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        pass
```

**If the plugin has settings**, add a settings class in the same file:

```python
from pydantic_settings import SettingsConfigDict
from screamingface.plugin import Plugin, PluginSettings


class <ClassName>Settings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_<UPPER_SNAKE>__",
        env_nested_delimiter="__",
    )
    # fields here


class <ClassName>Plugin(Plugin):
    name = "<kebab-name>"
    settings_class = <ClassName>Settings
    # ...
```

**If the plugin has routes**, create a separate `routes.py` file with a `create_router()` factory:

```python
# apps/server/src/screamingface/plugins/{snake_name}/routes.py
from __future__ import annotations

from fastapi import APIRouter


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/endpoint")
    async def endpoint():
        return {"status": "ok"}

    return router
```

And import it in `plugin.py`:

```python
from screamingface.plugins.<snake_name>.routes import create_router

class <ClassName>Plugin(Plugin):
    def setup(self, app, hooks, classes, routes):
        router = create_router()  # pass settings if needed
        routes.add_router(self.name, router, prefix="/<kebab-name>")
```

## File: `apps/server/tests/test_{snake_name}.py`

```python
"""Tests for the <kebab-name> plugin."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig


@pytest.fixture
def <fixture_name>_app() -> FastAPI:
    config = AppConfig(
        plugins=["<kebab-name>"],
        plugin_config={"<kebab-name>": {}},
    )
    return create_app(config)


@pytest.fixture
def <fixture_name>_client(<fixture_name>_app: FastAPI) -> TestClient:
    return TestClient(<fixture_name>_app)


def test_plugin_activates(<fixture_name>_app: FastAPI) -> None:
    assert "<kebab-name>" in <fixture_name>_app.state.plugins.active_plugins
```

Add route tests for each endpoint, following the patterns in `tests/test_proxy.py`.

## After generating files

1. Add the plugin to `sf.json` under `"plugins"` and `"plugin_config"`
2. Run `uv run pytest` to verify
3. Run `uv run ruff check --fix apps/server && uv run ruff format apps/server`

---

# Option B: External Plugin (standalone package)

If the user chose "external", generate a standalone package instead.

## File: `pyproject.toml` (in the new package root)

```toml
[project]
name = "screamingface-<kebab-name>"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "screamingface",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/screamingface_<snake_name>"]

[project.entry-points."screamingface.plugins"]
<kebab-name> = "screamingface_<snake_name>.plugin:<ClassName>Plugin"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[dependency-groups]
dev = [
    "pytest>=9.0",
    "screamingface",
]
```

## File: `src/screamingface_<snake_name>/__init__.py`

```python
"""<Description>."""

__version__ = "0.1.0"
```

## File: `src/screamingface_<snake_name>/plugin.py`

Same Plugin subclass as the built-in template above, but:
- Import `__version__` from the package's own `__init__.py`
- Set `version = __version__` on the class (external plugins do NOT inherit the core package version)

```python
from screamingface.plugin import Plugin
from screamingface_<snake_name> import __version__

class <ClassName>Plugin(Plugin):
    name = "<kebab-name>"
    version = __version__
    description = "<Description>"
    # ...
```

The import paths for core types are identical — the plugin imports from `screamingface.plugin` and `screamingface.core.*`.

If the plugin has routes, create `src/screamingface_<snake_name>/routes.py` with the same `create_router()` pattern but adjust the import in `plugin.py`:

```python
from screamingface_<snake_name>.routes import create_router
```

## File: `tests/test_plugin.py`

Same test structure as the built-in template.

## After generating files

1. Initialize the package: `cd screamingface-<kebab-name> && uv init` (if not already done)
2. Install in the server env for development: `cd apps/server && uv pip install -e /path/to/screamingface-<kebab-name>`
3. Verify: `sf plugin list` — should show `<kebab-name> [available] (entry-point)`
4. Enable: `sf plugin enable <kebab-name>`
5. Run tests: `uv run pytest`

---

## API Model Aliases (both types)

When a plugin exposes request/response Pydantic models, **every field must have a hand-picked short alias** via `Field(alias="...")`. This keeps API payloads and URL query params compact.

Rules:
- Aliases are **manually chosen** by the developer — never auto-generated. This ensures adding new fields later never changes existing aliases (which would break clients).
- Use word initials as a guideline: `system_prompt` → `sp`, `output_format` → `of`, `model` → `m`
- All API models must inherit from `AliasedModel` (from `screamingface.models`), which sets `populate_by_name=True` so both the long name and the short alias are accepted on input.
- Serialize responses with `model_dump(by_alias=True)` so output uses the short aliases.

```python
from pydantic import Field
from screamingface.models import AliasedModel


class MyRequest(AliasedModel):
    prompt: str = Field(alias="p")
    model: str | None = Field(None, alias="m")
    system_prompt: str | None = Field(None, alias="sp")
    max_retries: int = Field(3, alias="mr")
```

## Naming conventions (both types)

- Plugin name: `kebab-case` (e.g. `eval-runner`)
- Directory/package: `snake_case` (e.g. `eval_runner`)
- Package name (external): `screamingface-<kebab-name>` (e.g. `screamingface-eval-runner`)
- Class: `PascalCase` + `Plugin` suffix (e.g. `EvalRunnerPlugin`)
- Settings class: `PascalCase` + `Settings` suffix (e.g. `EvalRunnerSettings`)
- Env prefix: `SF_UPPER_SNAKE__` (e.g. `SF_EVAL_RUNNER__`)
- Test fixture: `snake_case` (e.g. `eval_runner_app`)

## Reference

See `apps/server/CONTRIBUTING.md` for full architecture docs. The reference plugin is `src/screamingface/plugins/claude_proxy/`.
