from __future__ import annotations

from copy import deepcopy
from typing import Any

from tortoise import Tortoise

DEFAULT_DATABASE_URL = "postgres://scoreboard:scoreboard@localhost:5432/scoreboard"

TORTOISE_CONFIG: dict[str, Any] = {
    "connections": {"default": DEFAULT_DATABASE_URL},
    "apps": {
        "models": {
            # scoreboard.scores.models is intentionally not registered yet.
            # Tortoise warns when an empty model module is registered; D-SCORE-002 adds
            # the first concrete model and registers the package at that point.
            "models": ["aerich.models"],
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
