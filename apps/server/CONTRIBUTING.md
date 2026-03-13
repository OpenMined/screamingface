# Contributing to ScreamingFace Server

## Setup

```bash
cd apps/server
uv sync          # install all dependencies (including dev)
sf --help        # verify CLI works
uv run pytest    # run tests
```

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

## Project Structure

```
apps/server/
├── src/screamingface/
│   ├── plugin.py          # Plugin + PluginSettings base classes
│   ├── core/
│   │   ├── app.py         # FastAPI factory (create_app)
│   │   ├── hooks.py       # HookRegistry — event/signal system
│   │   ├── classes.py     # ClassRegistry — Odoo-style _inherit
│   │   ├── routes.py      # RouteRegistry — dynamic router management
│   │   ├── registry.py    # PluginRegistry — discover/load/activate/deactivate
│   │   ├── config.py      # AppConfig + ServerConfig (Pydantic models)
│   │   └── ssl.py         # mkcert-based SSL auto-generation
│   ├── cli/
│   │   ├── main.py        # Typer root app (sf)
│   │   ├── run.py         # sf run — uvicorn launcher
│   │   └── plugin.py      # sf plugin list|info|enable|disable
│   └── plugins/           # Built-in plugins (auto-discovered)
│       └── claude_frontend/  # Reference plugin
├── tests/
├── sf.json                # Runtime config
└── pyproject.toml
```

## Architecture

The server is built on three independent extension registries. Plugins use any combination of them in their `setup()` method.

### HookRegistry — Events

Signal/event bus. Plugins subscribe to named hooks; the registry fires them.

```python
def setup(self, app, hooks, classes, routes):
    hooks.register("request.before", self.on_request, priority=50, plugin_name=self.name)
```

**Methods:**
- `register(hook_name, callback, *, priority=100, plugin_name="")` — lower priority runs first
- `emit(hook_name, **kwargs) → list` — fire all callbacks, collect returns
- `emit_async(hook_name, **kwargs) → list` — same but awaits coroutines
- `emit_chain(hook_name, value, **kwargs) → value` — pipeline: each callback receives the previous return value
- `unregister_plugin(plugin_name)` — remove all hooks for a plugin

**Built-in hooks:** `app.startup`, `app.shutdown`, `request.before`, `request.after`, `plugin.activated`, `plugin.deactivated`. Plugins can define any custom hook name.

### ClassRegistry — Composable Classes

Odoo-inspired runtime class composition. Register a base class under a dotted key, extend it with mixins from other plugins. `resolve()` builds the final class with proper MRO.

```python
def setup(self, app, hooks, classes, routes):
    # Plugin A registers a base
    classes.register("cache.CacheService", CacheService)

    # Plugin B extends it
    classes.extend("cache.CacheService", RedisCacheMixin, plugin_name=self.name)

# Anywhere later:
FinalCacheService = classes.resolve("cache.CacheService")
instance = FinalCacheService()
```

**Methods:**
- `register(key, cls)` — register base class (raises if key exists)
- `extend(key, mixin, *, plugin_name="")` — add mixin (last extension = highest MRO priority)
- `resolve(key) → type` — build and cache final composed class
- `unregister_plugin(plugin_name)` — remove all extensions from a plugin

### RouteRegistry — Dynamic Routes

Thin wrapper around FastAPI router inclusion. Tracks which plugin owns which routers so they can be removed at runtime.

```python
def setup(self, app, hooks, classes, routes):
    router = APIRouter()

    @router.get("/my-endpoint")
    async def my_endpoint():
        return {"hello": "world"}

    routes.add_router(self.name, router, prefix="/my-plugin")
```

**Methods:**
- `add_router(plugin_name, router, *, prefix="")` — include router, tagged with plugin name
- `remove_plugin_routes(plugin_name)` — remove all routes from a plugin
- `list_plugin_routes(plugin_name) → list[str]` — prefixes for a plugin
- `list_all_plugins() → list[str]` — plugin names with registered routes

## Configuration

`sf.json` is the single config file, readable by both Python and the Electron frontend.

```json
{
  "version": "0.1.0",
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "reload": true,
    "ssl": true
  },
  "plugins": ["claude-frontend"],
  "plugin_config": {
    "claude-frontend": {
      "upstream_url": "https://api.anthropic.com"
    }
  }
}
```

Plugin settings priority (highest wins): **env vars** → **sf.json** → **field defaults**.

## Application Lifecycle

`create_app()` in `core/app.py` assembles everything:

1. Load config from `sf.json`
2. Create HookRegistry, ClassRegistry, PluginRegistry
3. Create FastAPI app with lifespan (emits `app.startup`/`app.shutdown`)
4. Create RouteRegistry, attach all registries to `app.state`
5. Register HTTP middleware (emits `request.before`/`request.after`)
6. Register built-in endpoints (`/health`, `/plugins`, `/plugins/{name}/schema`, `/plugins/{name}/settings`)
7. Discover plugins (entry points + built-in scan)
8. Activate plugins in dependency order (topological sort)

All registries are accessible in route handlers via `request.app.state.hooks`, `.classes`, `.routes`, `.plugins`, `.config`.

## Contributing to Core

### Code Style

- Ruff for linting and formatting (config in `pyproject.toml`)
- Run before committing: `uv run ruff check --fix && uv run ruff format`
- Pre-commit hooks handle this automatically if installed: `uv run pre-commit install`

### Testing

```bash
uv run pytest              # run all tests
uv run pytest -v           # verbose
uv run pytest tests/test_hooks.py  # single module
uv run pytest -k "test_emit"      # by name pattern
```

**Test conventions:**
- Tests live in `tests/`, flat structure (no subdirectories)
- Shared fixtures in `conftest.py`: `hooks`, `classes`, `app`, `client`
- The `app` fixture creates a clean app with no plugins loaded
- Use `monkeypatch` for env var isolation
- Mock external HTTP with `unittest.mock.AsyncMock` + `patch()`

### Adding a Core Feature

1. Add implementation in the appropriate `core/` module
2. Write tests in `tests/test_<module>.py`
3. Run the full test suite
4. Update this doc if the public API changed

---

# Creating Plugins

## Quick Start — Built-in Plugin

Create a new directory under `src/screamingface/plugins/`:

```
src/screamingface/plugins/my_feature/
├── __init__.py      # empty
├── plugin.py        # required — contains your Plugin subclass
└── routes.py        # optional — route handlers
```

The `plugin.py` module is auto-discovered. Any `Plugin` subclass with a non-empty `name` attribute will be found.

### Minimal Plugin

```python
# src/screamingface/plugins/my_feature/plugin.py
from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin

if TYPE_CHECKING:
    from fastapi import FastAPI
    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class MyFeaturePlugin(Plugin):
    name = "my-feature"
    description = "Does something useful"

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        pass  # register hooks, classes, routes here
```

### Plugin with Settings

```python
from pydantic_settings import SettingsConfigDict
from screamingface.plugin import Plugin, PluginSettings


class MySettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_MY_FEATURE__",
        env_nested_delimiter="__",
    )
    some_option: str = "default_value"
    max_retries: int = 3


class MyFeaturePlugin(Plugin):
    name = "my-feature"
    version = "0.1.0"
    settings_class = MySettings

    def setup(self, app, hooks, classes, routes):
        # self.settings is populated automatically from sf.json + env vars
        print(self.settings.some_option)
```

Then add to `sf.json`:

```json
{
  "plugins": ["my-feature"],
  "plugin_config": {
    "my-feature": {
      "some_option": "custom_value"
    }
  }
}
```

### Plugin with Routes

```python
from fastapi import APIRouter

class MyFeaturePlugin(Plugin):
    name = "my-feature"

    def setup(self, app, hooks, classes, routes):
        router = APIRouter()

        @router.get("/status")
        async def status():
            return {"plugin": self.name, "status": "running"}

        @router.post("/action")
        async def do_action():
            return {"result": "done"}

        routes.add_router(self.name, router, prefix="/my-feature")
```

Routes will be available at `/my-feature/status` and `/my-feature/action`.

### Plugin with Hooks

```python
class MyFeaturePlugin(Plugin):
    name = "my-feature"

    def setup(self, app, hooks, classes, routes):
        # React to events
        hooks.register("app.startup", self.on_startup, plugin_name=self.name)
        hooks.register("request.before", self.on_request, priority=50, plugin_name=self.name)

        # Define custom hooks for other plugins to use
        hooks.register("my-feature.data.ready", self.on_data_ready, plugin_name=self.name)

    async def on_startup(self):
        print("My feature is starting up")

    async def on_request(self, request):
        print(f"Request: {request.method} {request.url.path}")

    def on_data_ready(self, data):
        return data
```

### Plugin with Class Extensions

```python
class MyFeaturePlugin(Plugin):
    name = "my-feature"

    def setup(self, app, hooks, classes, routes):
        # Register a base class
        classes.register("my-feature.Processor", BaseProcessor)

        # Or extend someone else's class
        classes.extend("other-plugin.Service", MyMixin, plugin_name=self.name)


class BaseProcessor:
    def process(self, data):
        return data


class MyMixin:
    def process(self, data):
        # super() chains to the base class
        data = super().process(data)
        return data.upper()
```

### Plugin with Dependencies

```python
class MyFeaturePlugin(Plugin):
    name = "my-feature"
    depends = ["claude-frontend"]  # activated after claude-frontend

    def setup(self, app, hooks, classes, routes):
        # Safe to access claude-frontend's registrations here
        pass
```

### Plugin with System Dependencies

```python
class MyFeaturePlugin(Plugin):
    name = "my-feature"
    system_deps = ["ffmpeg", "imagemagick"]  # checked via shutil.which()
```

Activation fails with a clear error if any tool is missing from PATH.

### Plugin Teardown

```python
class MyFeaturePlugin(Plugin):
    name = "my-feature"

    def setup(self, app, hooks, classes, routes):
        self._hooks = hooks
        self._classes = classes
        self._routes = routes
        hooks.register("app.startup", self.on_startup, plugin_name=self.name)
        routes.add_router(self.name, self.create_router())

    def teardown(self):
        # Clean up your registrations
        self._hooks.unregister_plugin(self.name)
        self._classes.unregister_plugin(self.name)
        self._routes.remove_plugin_routes(self.name)
```

## Testing Plugins

```python
# tests/test_my_feature.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig


@pytest.fixture
def my_app() -> FastAPI:
    config = AppConfig(
        plugins=["my-feature"],
        plugin_config={"my-feature": {"some_option": "test_value"}},
    )
    return create_app(config)


@pytest.fixture
def my_client(my_app: FastAPI) -> TestClient:
    return TestClient(my_app)


def test_plugin_activates(my_app: FastAPI) -> None:
    assert "my-feature" in my_app.state.plugins.active_plugins


def test_status_endpoint(my_client: TestClient) -> None:
    resp = my_client.get("/my-feature/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
```

## External Plugins

External plugins are standalone Python packages, developed in their own repo. They're discovered automatically via entry points when installed in the same environment as ScreamingFace.

### Scaffold a new plugin package

```bash
mkdir screamingface-my-plugin && cd screamingface-my-plugin
uv init
```

### Project layout

```
screamingface-my-plugin/
├── pyproject.toml
├── src/
│   └── screamingface_my_plugin/
│       ├── __init__.py
│       ├── plugin.py       # Plugin subclass
│       └── routes.py       # optional
└── tests/
    └── test_plugin.py
```

### `pyproject.toml`

```toml
[project]
name = "screamingface-my-plugin"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "screamingface",       # depend on the server package
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/screamingface_my_plugin"]

# This is what makes discovery work:
[project.entry-points."screamingface.plugins"]
my-plugin = "screamingface_my_plugin.plugin:MyPlugin"
```

The entry point key (`my-plugin`) becomes the name used in `sf.json` and `sf plugin` commands. The value points to your `Plugin` subclass.

### `src/screamingface_my_plugin/__init__.py`

```python
"""My Plugin — does something useful."""

__version__ = "0.1.0"
```

### `src/screamingface_my_plugin/plugin.py`

```python
"""My Plugin — does something useful."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin
from screamingface_my_plugin import __version__

if TYPE_CHECKING:
    from fastapi import FastAPI
    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class MyPlugin(Plugin):
    name = "my-plugin"
    version = __version__
    description = "Does something useful"

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        pass  # register hooks, classes, routes here

    def teardown(self) -> None:
        pass  # clean up here
```

Built-in plugins automatically inherit the ScreamingFace package version. External plugins should define `__version__` in their own `__init__.py` and reference it in the Plugin class.

Everything from the [plugin features section above](#plugin-with-settings) applies — settings, routes, hooks, class extensions, dependencies, system deps all work identically.

### Install for development

From the ScreamingFace server directory:

```bash
cd apps/server
uv pip install -e /path/to/screamingface-my-plugin
```

Or add it as a path dependency in `apps/server/pyproject.toml` during development:

```toml
[project]
dependencies = [
    # ...existing deps...
    "screamingface-my-plugin @ file:///path/to/screamingface-my-plugin",
]
```

### Verify discovery

```bash
sf plugin list
# Should show: my-plugin [available] (entry-point)

sf plugin enable my-plugin
sf run
```

### Testing

Your test suite should depend on `screamingface` and use the same patterns:

```python
# tests/test_plugin.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig


@pytest.fixture
def app() -> FastAPI:
    config = AppConfig(
        plugins=["my-plugin"],
        plugin_config={"my-plugin": {}},
    )
    return create_app(config)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_activates(app: FastAPI) -> None:
    assert "my-plugin" in app.state.plugins.active_plugins
```

Add `screamingface` and `pytest` to your dev dependencies:

```toml
[dependency-groups]
dev = [
    "pytest>=9.0",
    "screamingface",
]
```

### Publishing

Once ready, publish to PyPI. Users install with:

```bash
uv pip install screamingface-my-plugin
sf plugin enable my-plugin
```

The naming convention `screamingface-*` is recommended so plugins are discoverable on PyPI.

## CLI

```bash
sf plugin list              # show all discovered plugins + status
sf plugin info my-feature   # show plugin details
sf plugin enable my-feature # add to sf.json and save
sf plugin disable my-feature # remove from sf.json and save
sf run                      # start server with configured plugins
sf run --enable my-feature  # override: only activate these plugins
sf run --disable my-feature # override: exclude these plugins
```
