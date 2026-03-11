"""FastAPI application factory."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response

from screamingface.core.classes import ClassRegistry
from screamingface.core.config import AppConfig
from screamingface.core.hooks import HookRegistry
from screamingface.core.registry import PluginRegistry
from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)

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
        yield
        await hooks.emit_async("app.shutdown")

    app = FastAPI(
        title="ScreamingFace",
        version=config.version,
        lifespan=lifespan,
    )

    routes = RouteRegistry(app)

    # Store registries on app state for access in routes/middleware
    app.state.hooks = hooks
    app.state.classes = classes
    app.state.routes = routes
    app.state.plugins = plugin_registry
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

    @app.get("/plugins")
    async def list_plugins() -> dict:
        """List all active plugins with metadata."""
        return {
            name: {
                "version": p.version,
                "description": p.description,
                "has_settings": p.settings_class is not None,
            }
            for name, p in app.state.plugins.active_plugins.items()
        }

    @app.get("/plugins/{name}/schema")
    async def plugin_schema(name: str) -> dict:
        """Return JSON Schema for a plugin's settings."""
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin:
            raise HTTPException(404, f"Plugin {name!r} not active")
        if not plugin.settings_class:
            raise HTTPException(404, f"Plugin {name!r} has no configurable settings")
        return plugin.settings_class.model_json_schema()

    @app.get("/plugins/{name}/settings")
    async def plugin_settings(name: str) -> dict:
        """Return current resolved settings for a plugin."""
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin or not plugin.settings:
            raise HTTPException(404, f"Plugin {name!r} not found or has no settings")
        return plugin.settings.model_dump()

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

    return app
