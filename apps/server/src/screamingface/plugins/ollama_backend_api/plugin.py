"""ollama-backend-api plugin — direct Ollama ``/api/chat`` backend.

Most behavior lives in :class:`backend_api_base.BackendApiPluginBase`.
This module declares Ollama-specific settings (``base_url`` + optional
``api_key``) and overrides only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.backend_api_base import (
    BackendApiPluginBase,
    BackendApiSettingsBase,
)
from screamingface.plugins.ollama_backend_api.routes import create_route_bundle, create_router

if TYPE_CHECKING:
    from fastapi import FastAPI


class OllamaBackendApiSettings(BackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_OLLAMA_BACKEND_API__",
        env_nested_delimiter="__",
    )

    base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server base URL. Defaults to the local daemon.",
    )
    api_key: str | None = Field(
        default=None,
        description=(
            "Optional bearer token sent as ``Authorization: Bearer <key>`` "
            "on every request. Local Ollama usually needs no auth; this "
            "is for hardened remote deployments."
        ),
    )
    default_model: str | None = Field(
        default=None,
        description=("Default Ollama model. Falls back to 'llama3.2' if still unset at call time."),
    )


class OllamaBackendApiPlugin(BackendApiPluginBase):
    name = "ollama-backend-api"
    description = (
        "Direct Ollama API backend — POSTs to a local (or remote) Ollama "
        "server at /api/chat. Same route shapes as claude-backend-api but "
        "at /ollama/* prefix."
    )
    tags: list[str] = ["product:ollama"]
    depends: list[str] = ["llm-base", "backend-api-base"]
    conflicts: list[str] = []
    backend_call_paths: list[str] = ["/ollama"]
    settings_class = OllamaBackendApiSettings

    schema_link_base = "/ollama/"
    create_route_bundle = staticmethod(create_route_bundle)
    create_router = staticmethod(create_router)

    def _make_interpreter(self, app: FastAPI):
        from screamingface.plugins.ollama_backend_api.interpreter import (
            OllamaBackendApiInterpreter,
        )

        return OllamaBackendApiInterpreter(
            app=app,
            settings=self.settings,  # type: ignore[arg-type]
        )
