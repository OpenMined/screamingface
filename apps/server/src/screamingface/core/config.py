"""JSON configuration with Pydantic validation."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path("sf.json")


class ServerConfig(BaseModel):
    """Server-specific settings."""

    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False


class AppConfig(BaseModel):
    """Top-level application configuration."""

    version: str = "0.1.0"
    server: ServerConfig = Field(default_factory=ServerConfig)
    plugins: list[str] = Field(default_factory=list)
    plugin_config: dict[str, dict[str, object]] = Field(default_factory=dict)


def load_config(path: Path | None = None) -> AppConfig:
    """Load config from a JSON file, falling back to defaults."""
    config_path = path or DEFAULT_CONFIG_PATH
    if config_path.exists():
        data = json.loads(config_path.read_text())
        return AppConfig.model_validate(data)
    return AppConfig()


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Write config back to JSON file."""
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.write_text(json.dumps(config.model_dump(), indent=2) + "\n")
