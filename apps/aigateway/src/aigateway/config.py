from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIGW_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 9105
    log_level: str = "info"
