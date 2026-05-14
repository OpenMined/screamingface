"""aigw-codex-backend plugin - Codex served via the local AI Gateway."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.aigw_base import (
    AigwBackendApiPluginBase,
    AigwBackendApiSettingsBase,
)
from screamingface.plugins.aigw_codex_backend.routes import create_router

_CODEX_MODEL_SUGGESTIONS = [
    "codex/gpt-5.5",
    "codex/gpt-5.4",
    "codex/gpt-5.4-mini",
    "codex/gpt-5.3-codex",
    "codex/gpt-5.2",
]


class AigwCodexBackendSettings(AigwBackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_CODEX_BACKEND__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default="codex/gpt-5.4-mini",
        description=(
            "Default Codex model. The gateway routes by the prefix; "
            "must start with 'codex/'. Pick from the dropdown or type a "
            "custom slug if the gateway already supports it."
        ),
        examples=_CODEX_MODEL_SUGGESTIONS,
    )


class AigwCodexBackendPlugin(AigwBackendApiPluginBase):
    name = "aigw-codex-backend"
    description = (
        "Codex served at /codex via the local AI Gateway. The gateway reads "
        "file-backed Codex CLI auth and exposes import-based profile setup. "
        "Mutually exclusive with codex-backend-api because both own /codex."
    )
    tags: list[str] = ["product:openai"]
    backend_call_paths: list[str] = ["/codex"]
    conflicts: list[str] = ["codex-backend-api"]
    gateway_provider = "codex"
    auth_kind: ClassVar[str] = "import"
    settings_class = AigwCodexBackendSettings
    schema_link_base = "/codex/"
    create_router = staticmethod(create_router)
