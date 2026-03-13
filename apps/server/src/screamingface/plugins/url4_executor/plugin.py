"""URL4 Executor plugin — url4 protocol engine, parsing, resolution, and HTTP endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import field_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.url4_executor.routes import create_router
from screamingface.plugins.url4_executor.url4 import parse

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class Url4ExecutorSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_URL4_EXECUTOR__",
        env_nested_delimiter="__",
    )
    expression: str = ""

    @field_validator("expression")
    @classmethod
    def _validate_expression(cls, v: str) -> str:
        if not v:
            return v
        try:
            parse(v)
        except Exception as exc:
            raise ValueError(f"Invalid url4 expression: {exc}") from exc
        return v


class Url4ExecutorPlugin(Plugin):
    name = "url4-executor"
    description = "url4 protocol engine — parsing, resolution, and HTTP endpoint"
    depends: list[str] = []
    settings_class = Url4ExecutorSettings

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        router = create_router()
        routes.add_router(self.name, router, prefix="")
