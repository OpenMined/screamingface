"""gemini-backend-api plugin — Google AI Gemini API implementation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.gemini_backend_api.models import ClaudeProfile
from screamingface.plugins.gemini_backend_api.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


_PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class GeminiBackendApiSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_GEMINI_BACKEND_API__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default=None,
        description="Default Gemini model. Falls back to 'gemini-2.5-flash'.",
    )
    default_effort: str = Field(default="medium")
    interpreter_system_prompt: str = Field(
        default=(
            "You are a helpful assistant. Answer the user's question based only on "
            "the provided context. Be concise and factual."
        ),
    )
    timeout_seconds: float = Field(default=300.0)
    max_budget_usd: float | None = Field(default=None)
    permission_mode: str | None = Field(default=None)
    dangerously_skip_permissions: bool = Field(default=False)
    profiles: dict[str, ClaudeProfile] = Field(default_factory=dict)
    default_profile: str = Field(default="default")

    @field_validator("profiles")
    @classmethod
    def _validate_profile_keys(cls, v: dict[str, ClaudeProfile]) -> dict[str, ClaudeProfile]:
        for key in v:
            if not _PROFILE_NAME_RE.match(key):
                msg = f"Invalid profile name {key!r}"
                raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _validate_default_profile(self) -> GeminiBackendApiSettings:
        if self.default_profile and self.profiles and self.default_profile not in self.profiles:
            msg = (
                f"default_profile {self.default_profile!r} not found in profiles. "
                f"Available: {list(self.profiles.keys())}"
            )
            raise ValueError(msg)
        return self


class GeminiBackendApiPlugin(Plugin):
    name = "gemini-backend-api"
    description = "Direct Google AI Gemini API backend for ensemble fan-out"
    depends: list[str] = ["llm-base"]
    conflicts: list[str] = []
    backend_call_paths: list[str] = ["/gemini"]
    settings_class = GeminiBackendApiSettings

    def customize_schema(self, schema: dict) -> dict:
        settings: GeminiBackendApiSettings = self.settings  # type: ignore[assignment]
        profile_names = list(settings.profiles.keys())
        props = schema.get("properties", {})
        if profile_names and "default_profile" in props:
            props["default_profile"]["enum"] = profile_names
        if "profiles" in props:
            props["profiles"]["x-link-base"] = "/gemini/"
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
        from screamingface.plugins.gemini_backend_api.interpreter import (
            GeminiBackendApiInterpreter,
        )

        interpreter = GeminiBackendApiInterpreter(
            app=app,
            settings=self.settings,  # type: ignore[arg-type]
        )
        return await interpreter.process(sources="", intent=intent)
