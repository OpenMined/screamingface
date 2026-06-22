from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "sqlite://./scoreboard.sqlite3"


def normalize_database_url(database_url: str) -> str:
    sqlite_absolute_prefix = "sqlite:///"
    if not database_url.startswith(sqlite_absolute_prefix):
        return database_url

    path = database_url.removeprefix(sqlite_absolute_prefix)
    if not path or "/" in path:
        return database_url

    # Accept the common SQLite relative-file spelling instead of writing to /.
    return f"sqlite://./{path}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCOREBOARD_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 9106
    log_level: str = "info"
    database_url: str = DEFAULT_DATABASE_URL
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    portal_dir: Path | None = None
    portal_artifacts_dir: Path | None = None

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, database_url: str) -> str:
        return normalize_database_url(database_url)
