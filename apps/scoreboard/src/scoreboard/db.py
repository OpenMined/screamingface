from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from tortoise import Tortoise

from .config import DEFAULT_DATABASE_URL, normalize_database_url

DEFAULT_CONFIGURED_DATABASE_URL = normalize_database_url(
    os.getenv("SCOREBOARD_DATABASE_URL", DEFAULT_DATABASE_URL)
)

TORTOISE_CONFIG: dict[str, Any] = {
    "connections": {"default": DEFAULT_CONFIGURED_DATABASE_URL},
    "apps": {
        "models": {
            "models": ["scoreboard.scores.models"],
            "migrations": "scoreboard.scores.migrations",
            "default_connection": "default",
        }
    },
    "use_tz": True,
    "timezone": "UTC",
}


def build_tortoise_config(database_url: str) -> dict[str, Any]:
    config = deepcopy(TORTOISE_CONFIG)
    config["connections"]["default"] = database_url
    return config


async def init_db(database_url: str) -> None:
    # ASGI lifespan can initialize Tortoise in a different task than request handlers.
    # The global fallback keeps that initialized context visible across those tasks.
    await Tortoise.init(config=build_tortoise_config(database_url), _enable_global_fallback=True)


async def close_db() -> None:
    await Tortoise.close_connections()
