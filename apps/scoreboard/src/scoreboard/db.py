from __future__ import annotations

import warnings
from copy import deepcopy
from typing import Any

from tortoise import Tortoise

DEFAULT_DATABASE_URL = "postgres://scoreboard:scoreboard@localhost:5432/scoreboard"
EMPTY_SCORE_MODELS_WARNING = 'Module "scoreboard.scores.models" has no models'

TORTOISE_CONFIG: dict[str, Any] = {
    "connections": {"default": DEFAULT_DATABASE_URL},
    "apps": {
        "models": {
            # D-SCORE-002 adds the first concrete model to this reserved package.
            "models": ["scoreboard.scores.models"],
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
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=EMPTY_SCORE_MODELS_WARNING,
            category=RuntimeWarning,
        )
        await Tortoise.init(
            config=build_tortoise_config(database_url), _enable_global_fallback=True
        )


async def close_db() -> None:
    await Tortoise.close_connections()
