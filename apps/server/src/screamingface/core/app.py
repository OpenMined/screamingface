"""FastAPI application factory."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from screamingface.core.admin_router import register_admin_routes
from screamingface.core.classes import ClassRegistry
from screamingface.core.config import AppConfig
from screamingface.core.frontend import FrontendRegistry
from screamingface.core.hooks import HookRegistry
from screamingface.core.registry import PluginRegistry
from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


# Stash for CLI-resolved config. When uvicorn uses factory=True, it calls
# create_app() with no args. This lets run.py pass its fully-resolved
# config (with CLI overrides, auto-port, plugin filtering) to the factory.
_pending_config: AppConfig | None = None


def _resolve_config(config: AppConfig | None) -> AppConfig:
    """Resolve runtime config from arg → pending → env var → sf.json."""
    global _pending_config  # noqa: PLW0603
    if config is not None:
        return config
    if _pending_config is not None:
        out, _pending_config = _pending_config, None
        return out
    raw = os.environ.pop("_SF_RUNTIME_CONFIG", "")
    if raw:
        return AppConfig.model_validate_json(raw)
    from screamingface.core.config import load_config

    return load_config()


def _build_lifespan(hooks: HookRegistry, config: AppConfig):
    """Lifespan context manager: emits app.startup/shutdown + ready event."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await hooks.emit_async("app.startup")
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

    return lifespan


def _activate_plugins(
    config: AppConfig,
    plugin_registry: PluginRegistry,
    *,
    app: FastAPI,
    hooks: HookRegistry,
    classes: ClassRegistry,
    routes: RouteRegistry,
) -> None:
    """Discover plugins, activate the configured set, and clean up stale ones."""
    plugin_registry.discover()
    if config.plugins:
        available = set(plugin_registry.discovered_plugins.keys())
        to_activate = [p for p in config.plugins if p in available]
        missing = [p for p in config.plugins if p not in available]
        if missing:
            logger.warning("Plugins not found (skipping): %s", missing)
        if to_activate:
            plugin_registry.activate_all(
                to_activate, app=app, hooks=hooks, classes=classes, routes=routes
            )

    # Side-effect cleanup for previously-active-but-now-disabled plugins
    # (shell profile entries, /etc/hosts modifications, etc.)
    inactive = set(plugin_registry.discovered_plugins.keys()) - set(
        plugin_registry.active_plugins.keys()
    )
    for name in inactive:
        try:
            plugin_registry.load_plugin(name).cleanup_stale()
        except Exception:
            logger.debug("cleanup_stale for %s failed (non-fatal)", name, exc_info=True)


def create_app(config: AppConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application with all registries."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    config = _resolve_config(config)

    hooks = HookRegistry()
    classes = ClassRegistry()
    plugin_registry = PluginRegistry()

    app = FastAPI(
        title="ScreamingFace",
        version=config.version,
        lifespan=_build_lifespan(hooks, config),
    )

    routes = RouteRegistry(app)
    frontends = FrontendRegistry()

    app.state.hooks = hooks
    app.state.classes = classes
    app.state.routes = routes
    app.state.plugins = plugin_registry
    app.state.frontends = frontends
    app.state.config = config

    @app.middleware("http")
    async def hook_middleware(request: Request, call_next: object) -> Response:
        await hooks.emit_async("request.before", request=request)
        response = await call_next(request)  # type: ignore[operator]
        await hooks.emit_async("request.after", request=request, response=response)
        return response

    register_admin_routes(app)

    _activate_plugins(
        config,
        plugin_registry,
        app=app,
        hooks=hooks,
        classes=classes,
        routes=routes,
    )

    return app
