from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .db import close_db, init_db
from .routes import health, scores
from .scores.store import ScoreStore


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db(app.state.settings.database_url)
    try:
        yield
    finally:
        await close_db()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    app = FastAPI(title="scoreboard", version="0.1.0", lifespan=_lifespan)
    app.state.settings = settings
    app.state.score_store = ScoreStore()

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.include_router(scores.router)
    return app


app = create_app()
