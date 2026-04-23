"""ollama-backend-api plugin — direct Ollama ``/api/chat`` backend.

Declares:

- ``depends = ["llm-base"]`` — needs the shared ABCs and message shapes.
- ``conflicts = []`` — coexists with the other ``*_backend_api`` plugins
  so all can participate in ensemble fan-out.

Exposes routes at ``/ollama/run``, ``/ollama``, ``/ollama/{profile_name}``
mirroring the claude-backend-api route pattern. Transport is httpx POST
to a local (or remote) Ollama server.

Settings mirror claude-backend-api field-for-field plus two Ollama-
specific additions: ``base_url`` (the Ollama server URL) and ``api_key``
(optional bearer token). Env prefix is ``SF_OLLAMA_BACKEND_API__`` so
env-var overrides stay independent.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.ollama_backend_api.models import BackendProfile
from screamingface.plugins.ollama_backend_api.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


_PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class OllamaBackendApiSettings(PluginSettings):
    """Settings for ollama-backend-api.

    Mirrors ``ClaudeBackendApiSettings`` in all user-visible field names.
    CLI-only settings are accepted but silently ignored at request time.
    Adds two Ollama-specific fields: ``base_url`` and ``api_key``.
    """

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
        description=(
            "Default Ollama model for requests that don't specify one. "
            "Falls back to 'llama3.2' if still unset at call time."
        ),
    )
    default_effort: str = Field(
        default="medium",
        description="Default effort level.",
    )
    interpreter_system_prompt: str = Field(
        default=(
            "You are a helpful assistant. Answer the user's question based only on "
            "the provided context. Be concise and factual."
        ),
        description="System prompt used by the /ollama?q= url4 interpreter endpoint.",
    )
    timeout_seconds: float = Field(
        default=300.0,
        description="Default request timeout in seconds (httpx read timeout).",
    )
    max_budget_usd: float | None = Field(
        default=None,
        description=(
            "CLI-only budget cap. Accepted for sf.json compatibility but "
            "silently ignored by the direct-API backend."
        ),
    )
    permission_mode: str | None = Field(
        default=None,
        description=(
            "CLI-only setting. Accepted for sf.json compatibility but "
            "silently ignored by the direct-API backend."
        ),
    )
    dangerously_skip_permissions: bool = Field(
        default=False,
        description=(
            "CLI-only setting. Accepted for sf.json compatibility but "
            "silently ignored by the direct-API backend."
        ),
    )
    profiles: dict[str, BackendProfile] = Field(
        default_factory=dict,
        description="Named pre-configured execution profiles.",
    )
    default_profile: str = Field(
        default="default",
        description="Profile to use when none is specified. Must exist in profiles.",
    )

    @field_validator("profiles")
    @classmethod
    def _validate_profile_keys(cls, v: dict[str, BackendProfile]) -> dict[str, BackendProfile]:
        for key in v:
            if not _PROFILE_NAME_RE.match(key):
                msg = (
                    f"Invalid profile name {key!r}: must be lowercase "
                    "alphanumeric, hyphens, or underscores, starting with "
                    "a letter or digit."
                )
                raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _validate_default_profile(self) -> OllamaBackendApiSettings:
        if self.default_profile and self.profiles and self.default_profile not in self.profiles:
            msg = (
                f"default_profile {self.default_profile!r} not found in profiles. "
                f"Available: {list(self.profiles.keys())}"
            )
            raise ValueError(msg)
        return self


class OllamaBackendApiPlugin(Plugin):
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

    def customize_schema(self, schema: dict) -> dict:
        settings: OllamaBackendApiSettings = self.settings  # type: ignore[assignment]
        profile_names = list(settings.profiles.keys())
        props = schema.get("properties", {})
        if profile_names and "default_profile" in props:
            props["default_profile"]["enum"] = profile_names
        if "profiles" in props:
            props["profiles"]["x-link-base"] = "/ollama/"
        return schema

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        router = create_router(self.settings, app)  # type: ignore[arg-type]
        routes.add_router(self.name, router, prefix="")

    async def handle_backend_call(self, intent: str, *, app: FastAPI) -> str:
        """Dispatch a url4 backend-call to Ollama.

        Constructs an :class:`OllamaBackendApiInterpreter` and delegates
        to its ``process(sources="", intent=...)`` method.
        """
        from screamingface.plugins.ollama_backend_api.interpreter import (
            OllamaBackendApiInterpreter,
        )

        interpreter = OllamaBackendApiInterpreter(
            app=app,
            settings=self.settings,  # type: ignore[arg-type]
        )
        return await interpreter.process(sources="", intent=intent)
