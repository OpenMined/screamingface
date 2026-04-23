"""codex-backend-api plugin -- OpenAI Chat Completions API implementation.

Declares:

- ``depends = ["llm-base"]`` -- needs the shared ABCs and credential store
- ``conflicts = []`` -- coexists with claude-backend-api so both can
  participate in ensemble fan-out

Exposes routes at ``/codex/run``, ``/codex``, ``/codex/{profile_name}``
mirroring the claude-backend-api route pattern. Only the backend
differs -- httpx POST to api.openai.com instead of api.anthropic.com.

Settings mirror claude-backend-api field-for-field. Env prefix is
``SF_CODEX_BACKEND_API__`` so env-var overrides stay independent.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.codex_backend_api.models import BackendProfile
from screamingface.plugins.codex_backend_api.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


_PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class CodexBackendApiSettings(PluginSettings):
    """Settings for codex-backend-api.

    Mirrors ``ClaudeBackendApiSettings`` in all user-visible field names.
    CLI-only settings are accepted but silently ignored at request time.
    """

    model_config = SettingsConfigDict(
        env_prefix="SF_CODEX_BACKEND_API__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default=None,
        description=(
            "Default OpenAI model for requests that don't specify one. "
            "Falls back to 'o4-mini' if still unset at call time."
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
        description="System prompt used by the /codex?q= url4 interpreter endpoint.",
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
    def _validate_default_profile(self) -> CodexBackendApiSettings:
        if self.default_profile and self.profiles and self.default_profile not in self.profiles:
            msg = (
                f"default_profile {self.default_profile!r} not found in profiles. "
                f"Available: {list(self.profiles.keys())}"
            )
            raise ValueError(msg)
        return self


class CodexBackendApiPlugin(Plugin):
    name = "codex-backend-api"
    description = (
        "Direct OpenAI Chat Completions API backend -- reads OAuth token "
        "from the Codex CLI credential store (~/.codex/auth.json). "
        "Same route shapes as claude-backend-api but at /codex/* prefix."
    )
    depends: list[str] = ["llm-base", "backend-api-base"]
    conflicts: list[str] = []
    backend_call_paths: list[str] = ["/codex"]
    settings_class = CodexBackendApiSettings

    def customize_schema(self, schema: dict) -> dict:
        settings: CodexBackendApiSettings = self.settings  # type: ignore[assignment]
        profile_names = list(settings.profiles.keys())
        props = schema.get("properties", {})
        if profile_names and "default_profile" in props:
            props["default_profile"]["enum"] = profile_names
        if "profiles" in props:
            props["profiles"]["x-link-base"] = "/codex/"
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

    async def handle_backend_call(self, intent: str, *, sources: str = "", app: FastAPI) -> str:
        """Dispatch a url4 backend-call to the OpenAI API.

        Constructs a :class:`CodexBackendApiInterpreter` and delegates to
        its ``process(sources, intent)`` method.
        """
        from screamingface.plugins.codex_backend_api.interpreter import (
            CodexBackendApiInterpreter,
        )

        interpreter = CodexBackendApiInterpreter(
            app=app,
            settings=self.settings,  # type: ignore[arg-type]
        )
        return await interpreter.process(sources=sources, intent=intent)
