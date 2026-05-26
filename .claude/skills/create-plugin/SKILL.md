---
description: Scaffold a new ScreamingFace server plugin with routes, hooks, settings, CLI, and tests
user_invocable: true
---

# Create ScreamingFace Plugin

**Almost every piece of functionality in this codebase is a plugin.** CLI tools, audits, request/response interception, HTTP routes, base libraries other plugins depend on, persistent state — all of it lives under `apps/server/src/screamingface/plugins/<name>/` with a `plugin.py` declaring a `Plugin` subclass. If you're tempted to add a top-level script or a standalone module instead of a plugin, stop and ask whether a plugin fits — almost always it does.

When invoked, ask the user for:
1. **Plugin type** — built-in (inside this repo) or external (standalone package)
2. **Plugin name** (kebab-case, e.g. `eval-runner`)
3. **Description** (one sentence)
4. **What it needs** — any combination of: CLI commands, routes, hooks, settings, class extensions, dependencies on other plugins, system deps
5. If it needs settings, ask what settings fields (name, type, default)
6. If it needs routes, ask what endpoints (method, path, brief purpose)
7. If it needs CLI commands, ask the sub-app name (the kebab token after `sf`) and what subcommands

---

# Decision tree: what kind of plugin am I building?

Pick the shape(s) that apply — a plugin can combine several. Each row lists the **hook** to use, the **reference plugin** to copy from, and a **one-line "use when"**.

| What you need | Hook / pattern | Reference plugin | Use when |
|---|---|---|---|
| **A CLI command under `sf`** | Override `Plugin.register_cli(cls, app)` and `app.add_typer(<your_typer_app>, name="...")`. | `plugins/claude_intercept`, `plugins/claude_env_intercept`, `plugins/plugin_audit` | You want users to run `uv run sf <your-name> <subcommand>`. **Don't create scripts under `tools/`, `scripts/`, or `apps/server/cli/` — make a plugin.** |
| **A "base library" other plugins depend on** | Plugin with `depends: list[str] = []`, no routes/hooks. Public surface lives in a sibling module (commonly `plugin_base.py`, `models.py`, `errors.py`) that other plugins import. | `plugins/aigw_base`, `plugins/llm_base`, `plugins/backend_api_base`, `plugins/frontend_base` | You're providing shared classes, adapters, or utilities that other plugins extend or call. Other plugins declare `depends = ["<your-name>"]`. |
| **Pre/post hooks on requests, lifecycle, etc.** | Use the `hooks: HookRegistry` arg in `setup()` to register callbacks. | `plugins/tracing`, `plugins/mitmproxy_intercept` | You want to observe or mutate request/response flow without owning the route. |
| **HTTP routes** | Use the `routes: RouteRegistry` arg in `setup()` with a `create_router()` factory in a sibling `routes.py`. | `plugins/url4_executor`, `plugins/claude_backend_api` | You're exposing endpoints under the main SF server. For a dedicated port + transparent proxy frontend, see the next row. |
| **A transparent proxy on its own port** | Subclass `FrontendPluginBase` (from `plugins/frontend_base`). | `plugins/claude_frontend`, `plugins/codex_frontend`, `plugins/gemini_frontend`, `plugins/ollama_frontend` | You're proxying a third-party API (Anthropic, OpenAI, etc.) and need a separate listen port. |
| **A backend adapter to an LLM provider** | Subclass `BackendApiPluginBase` (from `plugins/backend_api_base`). | `plugins/claude_backend_api`, `plugins/codex_backend_api`, `plugins/gemini_backend_api`, `plugins/ollama_backend_api` | You're implementing the contract to call a specific provider's API. |
| **Extend an existing class / register an implementation** | Use the `classes: ClassRegistry` arg in `setup()`. | `plugins/url4_executor`, `plugins/state` | You're providing an implementation of an abstract interface another plugin defined. |
| **Persistent state (sqlite, files)** | Depend on `state` plugin (`depends = ["state"]`) and use its store interface. | `plugins/eval_runs`, `plugins/session_service` | You need durable state across restarts. Don't roll your own — use the `state` plugin. |
| **Plugin-typed configuration** | Add a `settings_class` (PluginSettings subclass) on the plugin class. | almost every plugin with `settings_class = ...` | The user should be able to configure the plugin via env vars or `sf.json`. |

**Combining shapes is normal.** `plugin_audit` is CLI-only. `url4_executor` has routes + hooks + classes. `claude_frontend` is a transparent proxy + settings. Build the shape that matches the job.

**Never:**
- Put a CLI command directly inside `apps/server/src/screamingface/cli/`. The `cli/` directory hosts only the root typer app + the generic `plugin` / `run` subcommands. Plugin-specific CLI lives in the plugin's directory and is mounted via `register_cli`.
- Put a standalone script under `apps/server/tools/`, `apps/server/scripts/`, or the repo root for anything that touches plugin internals. Make a plugin and expose it via `register_cli` or `register_routes`.
- Duplicate logic that already lives in a "base library" plugin (e.g. don't re-implement OAuth strategies that `llm_base` provides — `depends = ["llm-base"]` and import).

---

# Pattern: CLI plugin (`register_cli` hook)

If the plugin's job is to add `sf <something>` commands, the shape is:

```
apps/server/src/screamingface/plugins/<snake_name>/
├── __init__.py        # empty
├── plugin.py          # Plugin subclass with register_cli
├── cli.py             # the typer.Typer() sub-app + commands
└── tests/
    └── test_<snake_name>.py
```

## File: `plugin.py`

```python
"""<Description>."""

from __future__ import annotations

import typer

from screamingface.plugin import Plugin


class <ClassName>Plugin(Plugin):
    name = "<kebab-name>"
    description = "<Description>"
    depends: list[str] = []  # add any plugins you import from in cli.py

    @classmethod
    def register_cli(cls, app: typer.Typer) -> None:
        from screamingface.plugins.<snake_name>.cli import <snake_name>_app

        app.add_typer(<snake_name>_app, name="<kebab-name>")
```

`register_cli` is a `@classmethod`; the registry calls it during CLI construction *before any plugin is activated* — so don't touch settings or runtime state here. Just mount your sub-app.

## File: `cli.py`

```python
"""Typer sub-app for the <kebab-name> plugin."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

<snake_name>_app = typer.Typer(
    help="<Description>",
    no_args_is_help=True,
)


@<snake_name>_app.command("<verb>")
def <verb>_command(
    some_path: Annotated[
        Path,
        typer.Option("--some-path", help="..."),
    ] = Path("default"),
) -> None:
    """<What this verb does>."""
    # Lazy-import heavy deps so `sf --help` stays fast:
    from screamingface.plugins.<snake_name>.logic import do_the_thing

    result = do_the_thing(some_path)
    typer.echo(result)
```

**Invocation pattern:** `uv run sf <kebab-name> <verb> --some-path ...`

**Why a separate `cli.py`:** `plugin.py` is imported by the registry at discovery time. Keeping CLI commands in `cli.py` lets `register_cli` lazy-import them only when CLI is being built.

**Test the CLI invocation** with `typer.testing.CliRunner` against `screamingface.cli.main:app`:

```python
from typer.testing import CliRunner
from screamingface.cli.main import app


def test_cli_invocation(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["<kebab-name>", "<verb>", "--some-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
```

This exercises the full plugin-discovery + `register_cli` path — proving the plugin is wired correctly, not just that the function works.

---

# Pattern: Base library plugin

If the plugin's job is to provide classes, adapters, or utilities that *other plugins import*, the shape is:

```
apps/server/src/screamingface/plugins/<snake_name>/
├── __init__.py            # may re-export the public API for convenience
├── plugin.py              # minimal Plugin subclass with depends = []
├── plugin_base.py         # public abstract base classes / adapters (the actual "library")
├── models.py              # shared Pydantic models (optional)
└── tests/
```

## `plugin.py` is intentionally minimal:

```python
"""<Description> — base library; other plugins declare depends = ["<kebab-name>"]."""

from __future__ import annotations

from screamingface.plugin import Plugin


class <ClassName>Plugin(Plugin):
    name = "<kebab-name>"
    description = "<Description> — provides shared classes for downstream plugins."
    depends: list[str] = []
```

## Other plugins consume the library by:

1. Declaring `depends = ["<your-kebab-name>"]` in their plugin.py (this is a **runtime activation contract** — the registry refuses to activate them if your plugin isn't active).
2. Importing from the public modules:
   ```python
   from screamingface.plugins.<your_snake>.plugin_base import <AbstractClass>
   ```

**Run `sf plugin-audit deps` after declaring depends** to catch mismatches between what's imported and what's declared.

**Common subclassing convention:** if your library exposes a `Plugin` subclass that other plugins should extend (rather than calling utility functions), put it in `plugin_base.py` as a `<Something>PluginBase(Plugin)` and document that downstream plugins subclass it. See `aigw_base/plugin_base.py` for the canonical example.

---

# Pattern: Hook plugin (request/lifecycle interception)

If the plugin observes or mutates request/response flow without owning the route, use the `hooks` arg in `setup`:

```python
class <ClassName>Plugin(Plugin):
    name = "<kebab-name>"
    description = "<Description>"

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        hooks.register("on_request", self._on_request)
        hooks.register("on_response", self._on_response)

    def _on_request(self, request) -> None:
        ...
```

Reference: `plugins/tracing/plugin.py`, `plugins/mitmproxy_intercept/plugin.py`.

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
