# ScreamingFace Server

Plugin-based Python server with an Odoo-inspired architecture.

## Quick Start

```bash
cd apps/server
uv sync
sf --help          # CLI
sf run             # Start server (reads sf.json)
uv run pytest      # Run tests
```

## Architecture

### Three Extension Systems

1. **HookRegistry** (`core/hooks.py`) — Signal/event system. Plugins register callbacks for named hooks with priorities. Supports `emit()` (broadcast), `emit_chain()` (pipeline), and `emit_async()`.

2. **ClassRegistry** (`core/classes.py`) — Odoo-style `_inherit`. Register base classes under dotted keys (e.g., `cache.CacheService`), extend them with mixins. `resolve()` builds a final class via `type()` with proper MRO so `super()` chains work.

3. **RouteRegistry** (`core/routes.py`) — Dynamic router management. Plugins add FastAPI routers; deactivation removes routes by rebuilding `app.router.routes`.

### Plugin Contract

Subclass `screamingface.plugin.Plugin` and implement `setup()`:

```python
class MyPlugin(Plugin):
    name = "my-plugin"
    version = "0.1.0"
    depends = []

    def setup(self, app, hooks, classes, routes):
        # Register hooks, classes, routes here
        pass
```

### Plugin Discovery

- Entry points group: `screamingface.plugins`
- Convention: packages named `screamingface-*`
- Each service in `services/<name>/` becomes a plugin package

### Configuration

- `sf.json` — JSON config (readable by both Python and Electron)
- Pydantic validation in `core/config.py`
- CLI flags override config values

## Development

- Python 3.12+, managed with uv
- Ruff for linting/formatting
- pytest for testing
