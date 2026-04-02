"""FastAPI application factory."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response

from screamingface.core.classes import ClassRegistry
from screamingface.core.config import AppConfig
from screamingface.core.frontend import FrontendRegistry
from screamingface.core.hooks import HookRegistry
from screamingface.core.registry import PluginRegistry
from screamingface.core.routes import RouteRegistry
from screamingface.plugin import Plugin

logger = logging.getLogger(__name__)


def _inject_tag_enums(schema: dict, active_plugins: dict[str, Plugin]) -> None:
    """Walk a JSON Schema and inject ``enum`` for fields whose name matches a plugin tag.

    Convention: if a string property's name matches a known tag (e.g. ``"frontend"``),
    the enum is set to the list of active plugin names carrying that tag.
    Operates in-place on ``schema`` (including ``$defs``).
    """
    # Build tag → [plugin_name, ...] map
    tag_map: dict[str, list[str]] = {}
    for p in active_plugins.values():
        for tag in p.tags:
            tag_map.setdefault(tag, []).append(p.name)
    if not tag_map:
        return

    def _walk(node: dict) -> None:
        props = node.get("properties", {})
        for field_name, field_schema in props.items():
            if field_schema.get("type") == "string" and field_name in tag_map:
                field_schema["enum"] = tag_map[field_name]
            # Recurse into nested objects
            if field_schema.get("type") == "object":
                _walk(field_schema)
            # Recurse into array items
            items = field_schema.get("items")
            if isinstance(items, dict) and items.get("type") == "object":
                _walk(items)

        # Also walk $defs / definitions
        for defn in node.get("$defs", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)
        for defn in node.get("definitions", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)

    _walk(schema)


def _collapse_nullable(schema: dict) -> None:
    """Collapse ``anyOf: [{type: T}, {type: "null"}]`` into ``{type: T}``.

    Pydantic emits this pattern for ``X | None`` fields.  RJSF interprets
    ``anyOf`` as a type-selector dropdown, which is confusing for simple
    nullable scalars.  Collapsing gives RJSF a plain typed field and lets
    ``_inject_tag_enums`` / ``_inject_examples`` match these fields too.
    """

    def _walk(node: dict) -> None:
        for field_schema in node.get("properties", {}).values():
            any_of = field_schema.get("anyOf")
            if isinstance(any_of, list) and len(any_of) == 2:
                non_null = [s for s in any_of if s.get("type") != "null"]
                if len(non_null) == 1:
                    del field_schema["anyOf"]
                    field_schema.update(non_null[0])
            # Recurse into nested objects
            if field_schema.get("type") == "object":
                _walk(field_schema)
            items = field_schema.get("items")
            if isinstance(items, dict) and items.get("type") == "object":
                _walk(items)
        for defn in node.get("$defs", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)
        for defn in node.get("definitions", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)

    _walk(schema)


def _get_process_names() -> list[str]:
    """Return sorted unique names of currently running processes."""
    try:
        out = subprocess.check_output(["ps", "-eo", "comm="], text=True, timeout=5)
        names: set[str] = set()
        for line in out.splitlines():
            name = line.strip().rsplit("/", 1)[-1]  # basename
            if name and not name.startswith("-"):
                names.add(name)
        return sorted(names)
    except Exception:
        return []


def _inject_examples(schema: dict, field_name: str, examples: list[str]) -> None:
    """Inject ``examples`` into string fields matching *field_name*.

    Uses JSON Schema ``examples`` (not ``enum``) so the value is a suggestion,
    not a strict constraint — the user can still type a custom value.
    """

    def _walk(node: dict) -> None:
        for fname, fschema in node.get("properties", {}).items():
            if fschema.get("type") == "string" and fname == field_name:
                fschema["examples"] = examples
            if fschema.get("type") == "object":
                _walk(fschema)
            items = fschema.get("items")
            if isinstance(items, dict) and items.get("type") == "object":
                _walk(items)
        for defn in node.get("$defs", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)
        for defn in node.get("definitions", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)

    _walk(schema)


# Stash for CLI-resolved config. When uvicorn uses factory=True, it calls
# create_app() with no args. This lets run.py pass its fully-resolved
# config (with CLI overrides, auto-port, plugin filtering) to the factory.
_pending_config: AppConfig | None = None


def create_app(config: AppConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application with all registries."""
    # Ensure app-level loggers are visible (uvicorn only configures its own).
    # Safe to call multiple times — basicConfig is a no-op if a handler exists.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
    global _pending_config  # noqa: PLW0603
    if config is None:
        config = _pending_config
        _pending_config = None  # consume it
    if config is None:
        # Check env var (survives uvicorn reloader fork)
        raw = os.environ.pop("_SF_RUNTIME_CONFIG", "")
        if raw:
            config = AppConfig.model_validate_json(raw)
    if config is None:
        from screamingface.core.config import load_config

        config = load_config()

    hooks = HookRegistry()
    classes = ClassRegistry()
    plugin_registry = PluginRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await hooks.emit_async("app.startup")
        # Subprocess mode: emit JSON ready event so parent process knows we're up
        if os.environ.get("_SF_SUBPROCESS"):
            ready = {
                "event": "ready",
                "host": config.server.host,
                "port": config.server.port,
                "pid": os.getpid(),
                "scheme": "https" if config.server.ssl else "http",
            }
            sys.stdout.write(json.dumps(ready) + "\n")
            sys.stdout.flush()
        yield
        await hooks.emit_async("app.shutdown")

    app = FastAPI(
        title="ScreamingFace",
        version=config.version,
        lifespan=lifespan,
    )

    routes = RouteRegistry(app)

    frontends = FrontendRegistry()

    # Store registries on app state for access in routes/middleware
    app.state.hooks = hooks
    app.state.classes = classes
    app.state.routes = routes
    app.state.plugins = plugin_registry
    app.state.frontends = frontends
    app.state.config = config

    # Hook middleware for request.before / request.after
    @app.middleware("http")
    async def hook_middleware(request: Request, call_next: object) -> Response:
        await hooks.emit_async("request.before", request=request)
        response = await call_next(request)  # type: ignore[operator]
        await hooks.emit_async("request.after", request=request, response=response)
        return response

    # Health check endpoint
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/system/processes")
    async def list_processes() -> list[str]:
        """Return unique names of currently running processes."""
        return _get_process_names()

    @app.get("/plugins")
    async def list_plugins() -> dict:
        """List all active plugins with metadata."""
        return {
            name: {
                "version": p.version,
                "description": p.description,
                "has_settings": p.settings_class is not None,
                "requires_root": p.requires_root,
                "depends": p.depends,
                "conflicts": p.conflicts,
                "tags": p.tags,
            }
            for name, p in app.state.plugins.active_plugins.items()
        }

    @app.get("/plugins/{name}/schema")
    async def plugin_schema(name: str) -> dict:
        """Return JSON Schema for a plugin's settings.

        Dynamically injects enum choices for fields that reference other
        plugins by tag (e.g. ``frontend`` fields get a list of active
        plugins tagged ``"frontend"``).
        """
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin:
            raise HTTPException(404, f"Plugin {name!r} not active")
        if not plugin.settings_class:
            raise HTTPException(404, f"Plugin {name!r} has no configurable settings")
        schema = plugin.settings_class.model_json_schema()
        _collapse_nullable(schema)
        _inject_tag_enums(schema, app.state.plugins.active_plugins)
        _inject_examples(schema, "process_filter", _get_process_names())
        schema = plugin.customize_schema(schema)
        return schema

    @app.get("/plugins/{name}/settings")
    async def plugin_settings(name: str) -> dict:
        """Return current resolved settings for a plugin.

        Re-reads sf.json on each call so changes from the desktop UI
        are visible immediately without a server restart.
        """
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin or not plugin.settings_class:
            raise HTTPException(404, f"Plugin {name!r} not found or has no settings")
        # Re-read from config file for fresh data
        from screamingface.core.config import load_config

        fresh_config = load_config()
        raw = fresh_config.plugin_config.get(name, {})
        try:
            fresh_settings = plugin.settings_class(**raw)
        except Exception:
            # Fall back to in-memory if parsing fails
            if not plugin.settings:
                raise HTTPException(404, f"Plugin {name!r} has no settings")
            return plugin.settings.model_dump()
        return fresh_settings.model_dump()

    @app.post("/plugins/{name}/settings")
    async def update_plugin_settings(name: str, request: Request) -> dict:
        """Update a plugin's in-memory settings at runtime."""
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin or not plugin.settings_class:
            raise HTTPException(404, f"Plugin {name!r} not found or has no settings")
        data = await request.json()
        plugin.settings = plugin.settings_class(**data)
        # Also update the in-memory config so other code sees the change
        app.state.config.plugin_config[name] = data
        return plugin.settings.model_dump()

    @app.post("/plugins/{name}/settings/validate")
    async def validate_plugin_settings(name: str, request: Request) -> dict:
        """Validate proposed plugin settings without persisting them."""
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin:
            raise HTTPException(404, f"Plugin {name!r} not active")
        if not plugin.settings_class:
            raise HTTPException(404, f"Plugin {name!r} has no configurable settings")
        body = await request.json()
        try:
            plugin.settings_class(**body)
            return {"valid": True}
        except Exception as exc:
            raise HTTPException(422, detail=str(exc)) from exc

    # Discover and activate plugins
    plugin_registry.discover()
    if config.plugins:
        available = set(plugin_registry.discovered_plugins.keys())
        to_activate = [p for p in config.plugins if p in available]
        missing = [p for p in config.plugins if p not in available]
        if missing:
            logger.warning("Plugins not found (skipping): %s", missing)
        if to_activate:
            plugin_registry.activate_all(
                to_activate,
                app=app,
                hooks=hooks,
                classes=classes,
                routes=routes,
            )

    # Clean up stale side effects from previously-active-but-now-disabled plugins
    # (e.g. shell profile entries, /etc/hosts modifications left behind when a
    # plugin was removed while the server wasn't running)
    inactive = set(plugin_registry.discovered_plugins.keys()) - set(
        plugin_registry.active_plugins.keys()
    )
    for name in inactive:
        try:
            plugin = plugin_registry.load_plugin(name)
            plugin.cleanup_stale()
        except Exception:
            logger.debug("cleanup_stale for %s failed (non-fatal)", name, exc_info=True)

    return app
