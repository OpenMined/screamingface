# ScreamingFace

An AI ensemble proxy where **every feature is a plugin**. The core is just plumbing.

**What does that actually mean?** The server itself doesn't know about Claude, Gemini, or any AI model. It knows how to discover plugins, call their `setup()`, and route HTTP requests. Plugins teach it what to do. Want to add Ollama support? Write a plugin. Want custom logging? Write a plugin. Want to cache responses to save money? You guessed it — write a plugin.

## Why plugins? Why this will work for us

### The situation we're in

We're building an AI ensemble that talks to Claude, Gemini, Codex, Ollama — and the list keeps growing. Every few months a new model drops and someone needs to integrate it.

We're a small core team at OpenMined, but we want dozens of open-source contributors. The AI landscape moves fast. APIs change, new capabilities appear, models get deprecated. We need an architecture that can absorb this chaos without collapsing.

### What goes wrong without plugins

In a monolith, adding Ollama support means editing the same routing code that handles Claude. One bad merge and Claude breaks too.

New contributor wants to add Gemini support. They have to understand the entire codebase just to add one backend. Most give up before they start.

You can't disable a feature without commenting out code. Users get everything whether they want it or not. Testing is all-or-nothing — you can't test Ollama integration without Claude's code loading too.

We've seen this movie. It ends with a tangled codebase that only the original authors can touch.

### How our plugin architecture solves this

**Each AI backend is its own plugin.** The Claude proxy lives in `plugins/claude_proxy/`. The Claude CLI wrapper lives in `plugins/claude_cli/`. Ollama would be `plugins/ollama/`. They share zero code. Break one, the others don't notice.

**New contributors touch one folder.** Want to add Gemini? Create `plugins/gemini/`, implement the Plugin interface, submit a PR. You don't need to understand how Claude's proxy works.

**The server doesn't pick favorites.** The core doesn't know what Claude is. It just knows how to discover plugins, call their `setup()`, and route requests. Today it's AI models; tomorrow someone could write a metrics plugin, a caching layer, or a rate limiter — same architecture.

**Users compose their own server.** A user who only needs Claude enables one plugin. A power user running a 4-model ensemble enables four. `sf.json` is the menu — no bloat, no wasted resources.

**Broken plugins don't crash the server.** If your plugin fails its health check (we call it `preflight`), the server logs a warning and keeps running. Other plugins are unaffected. This is critical for an open-source project — we can't let a community-contributed plugin take down the whole server.

**Automatic startup order.** If your plugin needs another plugin to be ready first, just set `depends = ["claude-proxy"]`. The server figures out the right startup order automatically using a topological sort (fancy term for "figure out what needs to go first, like sorting a recipe's steps so you don't try to frost a cake before baking it").

### The ecosystem play

We didn't build a plugin system because it's cool. We built it because we want **you** to add features we haven't thought of yet.

External plugins don't need our permission. You publish a Python package, users install it, done. Same discovery mechanism, same API, same testing patterns.

This is how VS Code, WordPress, and Odoo scaled to thousands of extensions. A small core team maintains the platform; the community builds the features.

The architecture is ready. The three built-in plugins prove it works. Now we need contributors to make it an ecosystem.

## The three extension systems

Plugins wire themselves into the server through three registries. You can use any combination of them.

### HookRegistry — Events

**Problem:** Plugin A needs to react when something happens in Plugin B, but they shouldn't import each other directly.

**Solution:** An event system. One plugin fires an event, others listen. You've seen this before — it's like `addEventListener('click', handler)` in JavaScript, but for server events.

```python
def setup(self, app, hooks, classes, routes):
    # Listen for an event
    hooks.register("request.before", self.on_request, plugin_name=self.name)

# Somewhere else in the server, this fires the event:
hooks.emit("request.before", request=request)
```

**Built-in events:**
| Event | When it fires |
|---|---|
| `app.startup` | Server is starting up |
| `app.shutdown` | Server is shutting down |
| `request.before` | An HTTP request just arrived |
| `request.after` | An HTTP response is about to be sent |
| `plugin.activated` | A plugin was just activated |
| `plugin.deactivated` | A plugin was just deactivated |

Plugins can also define their own custom events — just pick a name and `emit()` it.

### ClassRegistry — Composable classes

**Problem:** You want to add behavior to a class defined in another plugin, without editing their code.

**Solution:** Register a base class, then any plugin can "extend" it with extra methods. When someone uses the class, they get the combined version. Think of it like browser extensions — the browser works fine alone, but extensions add new behavior on top. Each extension doesn't know about the others, but they all work together.

```python
# Plugin A registers a base processor
class BaseProcessor:
    def process(self, data):
        return data

classes.register("myapp.Processor", BaseProcessor)

# Plugin B adds logging on top — no edits to Plugin A
class LoggingMixin:
    def process(self, data):
        print(f"Processing: {data}")
        return super().process(data)  # calls BaseProcessor.process()

classes.extend("myapp.Processor", LoggingMixin, plugin_name=self.name)

# When you need the class, resolve() gives you the combined version:
Processor = classes.resolve("myapp.Processor")
result = Processor().process("hello")
# prints "Processing: hello", then returns "hello"
```

The `super().process(data)` call is key — it means "call the original method from the base class." This is how the mixin layers its behavior on top without replacing the original.

### RouteRegistry — HTTP endpoints

**Problem:** Each plugin needs to add its own API endpoints, and they should disappear if the plugin is disabled.

**Solution:** Plugins register FastAPI routers. The registry tracks who owns what, so routes can be added and removed cleanly — like mounting a USB drive. Plug in the plugin, its endpoints appear; unplug it, they're gone.

```python
def setup(self, app, hooks, classes, routes):
    router = APIRouter()

    @router.get("/status")
    async def status():
        return {"plugin": self.name, "ok": True}

    routes.add_router(self.name, router, prefix="/my-plugin")
```

For the full API reference on all three registries, see [CONTRIBUTING.md](./CONTRIBUTING.md).

## Your first plugin in 5 minutes

Let's build a plugin that adds a single endpoint. Copy and paste these commands.

**1. Create the folder:**
```bash
mkdir -p src/screamingface/plugins/hello_world/
```

**2. Create an empty `__init__.py`:**
```bash
touch src/screamingface/plugins/hello_world/__init__.py
```

**3. Create `plugin.py`:**

```python
# src/screamingface/plugins/hello_world/plugin.py
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from screamingface.plugin import Plugin

if TYPE_CHECKING:
    from fastapi import FastAPI
    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class HelloWorldPlugin(Plugin):
    name = "hello-world"
    description = "A simple greeting endpoint"

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        router = APIRouter()

        @router.get("/")
        async def hello():
            return {"message": "Hello from my plugin!"}

        routes.add_router(self.name, router, prefix="/hello")
```

**4. Enable it in `sf.json`:**
```json
{
  "plugins": ["claude-proxy", "hello-world"]
}
```

**5. Run the server:**
```bash
sf run
```

**6. Test it:**
```bash
curl https://localhost:8000/hello/
# → {"message":"Hello from my plugin!"}
```

**7. See it listed:**
```bash
sf plugin list
# hello-world should show as active
```

**What just happened?** The server scans every folder under `plugins/` for a file called `plugin.py`. If it finds a class that inherits from `Plugin` with a `name` set, it's discovered automatically. No registration config, no import wiring — just drop in the folder and enable it.

## Contributing: two paths

### Path A: In-repo plugin (for core team and regular contributors)

Your plugin lives inside this repository under `src/screamingface/plugins/`. It's auto-discovered — no extra configuration needed. Submit a PR, get it reviewed, it ships with ScreamingFace.

**Built-in plugins to study:**
| Plugin | Folder | What it does |
|---|---|---|
| `claude-proxy` | `plugins/claude_proxy/` | Forwards requests to the Anthropic API |
| `claude-cli` | `plugins/claude_cli/` | Runs Claude Code CLI locally and wraps it as a REST endpoint |
| `url-executor` | `plugins/url_executor/` | Routes URL-encoded requests to the right backend |

### Path B: External plugin (your own package)

Choose this path when your plugin is specific to your company, experimental, or you want to version and release it independently.

**1. Create a new Python package:**
```
screamingface-my-plugin/
├── pyproject.toml
├── src/
│   └── screamingface_my_plugin/
│       ├── __init__.py
│       └── plugin.py
└── tests/
```

**2. Add an entry point to `pyproject.toml`:**

This is the one line that makes discovery work:
```toml
[project.entry-points."screamingface.plugins"]
my-plugin = "screamingface_my_plugin.plugin:MyPlugin"
```

Entry points are a standard Python mechanism. Think of it as registering your plugin in a phonebook. When ScreamingFace starts, it checks the phonebook for any installed plugins and loads them alongside the built-in ones. The key (`my-plugin`) becomes the name you use in `sf.json`.

**3. Point the entry to your Plugin class:**

```python
# src/screamingface_my_plugin/plugin.py
from screamingface.plugin import Plugin

class MyPlugin(Plugin):
    name = "my-plugin"
    version = "0.1.0"
    description = "My external plugin"

    def setup(self, app, hooks, classes, routes):
        pass  # your code here
```

**4. Install it alongside ScreamingFace:**

```bash
uv pip install screamingface-my-plugin           # from PyPI
uv pip install git+https://github.com/user/repo  # from GitHub
uv pip install -e ../my-local-plugin              # local development
```

No permission needed. Build it, publish it, users install it.

## Real-world walkthrough: `claude-cli` plugin

Let's look at an actual plugin from the codebase — `plugins/claude_cli/plugin.py`:

**The settings class** — these are the knobs users can tune. Each has a default value. Users override them via `sf.json` or environment variables.
```python
class ClaudeCliSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_CLI__",
        env_nested_delimiter="__",
    )
    default_model: str | None = None
    default_effort: str = "medium"
    timeout_seconds: float = 300.0
    max_budget_usd: float | None = None
    permission_mode: str | None = None
    dangerously_skip_permissions: bool = False
```

**`system_deps = ["claude"]`** — before the plugin starts, the server checks if `claude` is installed on the machine. If not, it skips the plugin with a warning instead of crashing. This is the `preflight` mechanism at work.

**The plugin class and `setup()` method** — this is where everything gets wired up. This plugin creates a FastAPI router with its endpoints and registers it with the route registry.
```python
class ClaudeCliPlugin(Plugin):
    name = "claude-cli"
    description = "REST wrapper for the local Claude Code CLI"
    settings_class = ClaudeCliSettings
    system_deps = ["claude"]

    def setup(self, app, hooks, classes, routes):
        router = create_router(self.settings)
        routes.add_router(self.name, router, prefix="")
```

That's the whole plugin definition. The `create_router` function (in a separate `routes.py` file) is standard FastAPI — if you know FastAPI, you know this. The plugin class is just the glue that connects your routes to the server's lifecycle.

## Configuration

### `sf.json`

The single config file, shared between the Python server and the Electron frontend:

```json
{
  "version": "0.1.0",
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "reload": true,
    "ssl": true
  },
  "plugins": ["claude-proxy"],
  "plugin_config": {
    "claude-proxy": {
      "upstream_url": "https://api.anthropic.com",
      "api_key_env": "ANTHROPIC_API_KEY"
    }
  }
}
```

- **`plugins`** — which plugins to activate (by name)
- **`plugin_config`** — per-plugin settings that override field defaults

### Plugin settings priority

Settings are resolved in this order (highest priority wins):

1. **Environment variables** — `SF_PLUGINNAME__SETTING` (e.g., `SF_CLAUDE_CLI__TIMEOUT_SECONDS=600`)
2. **`sf.json`** — the `plugin_config` section
3. **Field defaults** — what's defined in the settings class

Environment variables always win. This matters for Docker deployments, CI pipelines, and secrets you don't want in a config file.

### CLI quick reference

```bash
sf plugin list                  # show all discovered plugins + status
sf plugin info claude-proxy     # show plugin details
sf plugin enable my-plugin      # add to sf.json
sf plugin disable my-plugin     # remove from sf.json
sf run                          # start server with configured plugins
sf run --enable my-plugin       # override: activate only these
sf run --disable my-plugin      # override: exclude these
```

## The vision

ScreamingFace is built by [OpenMined](https://openmined.org). We want this to be an ecosystem, not a monolith. Fifty plugins from fifty contributors — each one adding a new AI backend, a new integration, a new capability that makes the ensemble smarter.

The architecture is in place. The plugin contract is stable. The three built-in plugins prove it works end to end.

Read [CONTRIBUTING.md](./CONTRIBUTING.md) for the full technical guide. Pick a plugin idea. Ship it.
