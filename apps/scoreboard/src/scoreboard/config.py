from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCOREBOARD_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 9106
    log_level: str = "info"
    database_url: str = "postgres://scoreboard:scoreboard@localhost:5432/scoreboard"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
