from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings
from .core.bootstrap import bootstrap_from_claude_code
from .core.loader import load_plugins
from .core.pending_auth import PendingAuthTable
from .core.profile_index import ProfileIndexStore
from .core.registry import ProviderRegistry
from .routes import auth, chat, health, models

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app):
    try:
        await bootstrap_from_claude_code(index_store=app.state.profile_index)
    except Exception:
        logger.exception("bootstrap failed; gateway will start with empty index")
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()
    app = FastAPI(title="aigateway", version="0.1.0", lifespan=_lifespan)
    app.state.settings = settings

    registry = ProviderRegistry()
    load_plugins(registry)
    app.state.providers = registry
    app.state.profile_index = ProfileIndexStore()
    app.state.pending_auth = PendingAuthTable(ttl_seconds=600)

    for plugin in registry.all():
        auth_router = plugin.auth_router()
        if auth_router is not None:
            app.include_router(auth_router, prefix=f"/v1/auth/{plugin.custom_llm_provider}")

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)

    logger.info("aigateway ready (port=%d, providers=%d)", settings.port, len(registry.all()))
    return app


app = create_app()
