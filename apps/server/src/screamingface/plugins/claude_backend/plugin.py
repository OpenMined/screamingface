"""Claude Backend plugin — REST wrapper for the local Claude Code CLI."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.claude_backend.models import ClaudeProfile
from screamingface.plugins.claude_backend.routes import create_router

_PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class ClaudeBackendSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_BACKEND__",
        env_nested_delimiter="__",
    )
    default_model: str | None = None
    default_effort: str = "medium"
    interpreter_system_prompt: str = Field(
        default=(
            "You are a helpful assistant. Answer the user's question based only on "
            "the provided context. Be concise and factual."
        ),
        description="System prompt used by the /claude?q= url4 interpreter endpoint.",
    )
    timeout_seconds: float = 300.0
    max_budget_usd: float | None = None
    permission_mode: str | None = None
    dangerously_skip_permissions: bool = False
    profiles: dict[str, ClaudeProfile] = Field(
        default_factory=dict,
        description="Named pre-configured Claude execution profiles.",
    )
    default_profile: str | None = Field(
        default=None,
        description="Profile to use when none is specified.",
    )

    @field_validator("profiles")
    @classmethod
    def _validate_profile_keys(cls, v: dict[str, ClaudeProfile]) -> dict[str, ClaudeProfile]:
        for key in v:
            if not _PROFILE_NAME_RE.match(key):
                msg = (
                    f"Invalid profile name {key!r}: must be lowercase alphanumeric, "
                    "hyphens, or underscores, starting with a letter or digit."
                )
                raise ValueError(msg)
        return v


class ClaudeBackendPlugin(Plugin):
    name = "claude-backend"
    description = "REST wrapper for the local Claude Code CLI"
    depends: list[str] = ["url4-executor"]
    settings_class = ClaudeBackendSettings
    system_deps = ["claude"]

    def customize_schema(self, schema: dict) -> dict:
        settings: ClaudeBackendSettings = self.settings  # type: ignore[assignment]
        profile_names = list(settings.profiles.keys())
        props = schema.get("properties", {})
        if profile_names and "default_profile" in props:
            props["default_profile"]["enum"] = profile_names
        if "profiles" in props:
            props["profiles"]["x-link-base"] = "/claude/"
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
