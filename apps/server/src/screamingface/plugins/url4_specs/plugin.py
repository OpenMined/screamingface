"""URL4 Specs plugin — named URL4 expression library with copyable links."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class Url4Spec(BaseModel):
    expression: str = Field(
        default="",
        description="A (url, intent) tuple that tells URL4 what to fetch and how to interpret it.",
        examples=[
            '("https://example.com", "extract main content")',
            '("https://api.example.com/data.json", "parse as JSON")',
            "(http://localhost:8000/api/v1/users, http://localhost:8000/api/v1/roles)"
            "!audit permissions",
            "(https://github.com/user/repo/raw/main/README.md,"
            " https://github.com/user/repo/raw/main/CHANGELOG.md)"
            "!extract breaking changes",
            "((http://localhost:3000/config.json,"
            " http://localhost:3000/schema.json),"
            " https://docs.example.com/api-spec)"
            "!validate config against spec",
        ],
        json_schema_extra={"x-placeholder": "(url, intent)"},
    )


class Url4SpecsSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_URL4_SPECS__",
        env_nested_delimiter="__",
    )

    specs: dict[str, Url4Spec] = Field(
        default_factory=dict,
        description="Each spec is a named URL4 expression you can share via a copyable link.",
    )


class Url4SpecsPlugin(Plugin):
    name = "url4-specs"
    description = "Named URL4 expression library with copyable links"
    depends: list[str] = []
    settings_class = Url4SpecsSettings

    def customize_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        props = schema.get("properties", {})
        if "specs" in props:
            props["specs"]["x-copy-link"] = {
                "path": "/ensemble",
                "param": "q",
                "field": "expression",
            }
        return schema

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        pass  # no routes needed — pure settings storage
