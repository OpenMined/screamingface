"""Ollama Frontend plugin — transparent proxy on a dedicated port.

Most behavior lives in :class:`frontend_base.FrontendPluginBase`. This
module declares the Ollama-specific overrides only.

Notable differences from the other frontends:
- No CLI binary check at preflight (Ollama is a server, not a CLI).
- ``embed_target`` defaults to ``"system"`` (others default to
  ``"user"``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.frontend_base import (
    FrontendPluginBase,
    FrontendSettingsBase,
)
from screamingface.plugins.ollama_frontend.proxy import create_router


class OllamaFrontendSettings(FrontendSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_OLLAMA_FRONTEND__",
        env_nested_delimiter="__",
    )

    upstream_url: str = "http://localhost:11434"
    listen_port: int = 9104
    default_backend_path: str = "/ollama"
    # Ollama frontend prefers system-prompt injection as the default
    # because its default chat template treats messages[0] specially.
    embed_target: Literal["system", "user"] = Field(default="system")


class OllamaFrontendPlugin(FrontendPluginBase):
    name = "ollama-frontend"
    description = "Transparent proxy between local clients and a local/remote Ollama server"
    tags: list[str] = ["product:ollama"]
    depends: list[str] = ["url4-specs", "url4-executor", "frontend-base"]
    settings_class = OllamaFrontendSettings

    # Ollama is a server, not a CLI — no preflight binary check.
    cli_binary = None
    app_title = "ollama-frontend"
    create_router = staticmethod(create_router)
