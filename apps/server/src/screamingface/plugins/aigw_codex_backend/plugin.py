"""aigw-codex-backend plugin — Codex served via the local AI Gateway."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.aigw_base import (
    AigwBackendApiPluginBase,
    AigwBackendApiSettingsBase,
)
from screamingface.plugins.aigw_codex_backend.routes import create_router


class AigwCodexBackendSettings(AigwBackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_CODEX_BACKEND__",
        env_nested_delimiter="__",
    )

    # `default_model` suggestions are derived live from the gateway's /v1/models
    # registry by AigwBackendApiPluginBase.customize_schema (SF-284) — not copied
    # here. Source of truth: apps/aigateway/.../codex_provider/models.py.
    default_model: str | None = Field(
        default="codex/gpt-5.4-mini",
        description=(
            "Default Codex model. The gateway routes by the prefix; "
            "must start with 'codex/'. Pick from the dropdown or type a "
            "custom slug if the gateway already supports it."
        ),
    )


class AigwCodexBackendPlugin(AigwBackendApiPluginBase):
    name = "aigw-codex-backend"
    description = (
        "Codex served at /codex via the local AI Gateway. Auth, refresh, "
        "profile storage, and provider adaptation live in the gateway; this "
        "plugin exposes the standard SF backend routes and browser OAuth proxy."
    )
    tags: list[str] = ["product:openai"]
    backend_call_paths: list[str] = ["/codex"]
    conflicts: list[str] = ["codex-backend-api"]
    gateway_provider = "codex"
    settings_class = AigwCodexBackendSettings
    schema_link_base = "/codex/"
    create_router = staticmethod(create_router)
