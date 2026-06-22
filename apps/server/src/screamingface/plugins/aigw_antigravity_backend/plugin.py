"""aigw-antigravity-backend plugin — experimental Antigravity via the AI Gateway."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.aigw_antigravity_backend.routes import create_router
from screamingface.plugins.aigw_base import (
    AigwBackendApiPluginBase,
    AigwBackendApiSettingsBase,
)


class AigwAntigravityBackendSettings(AigwBackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_ANTIGRAVITY_BACKEND__",
        env_nested_delimiter="__",
    )

    # `default_model` suggestions are derived live from the gateway's /v1/models
    # registry by AigwBackendApiPluginBase.customize_schema (SF-284) — not copied
    # here. Source of truth: apps/aigateway/.../antigravity_provider/settings.py.
    default_model: str | None = Field(
        default="antigravity/gemini-3.5-flash",
        description=(
            "Default Antigravity model. The gateway routes by the prefix; "
            "must start with 'antigravity/'. Pick from the dropdown or type a "
            "custom slug if the gateway already supports it."
        ),
    )


class AigwAntigravityBackendPlugin(AigwBackendApiPluginBase):
    name = "aigw-antigravity-backend"
    description = (
        "Experimental Antigravity (Google Code Assist) served at /antigravity "
        "via the local AI Gateway. Auth, refresh, profile storage, and provider "
        "adaptation live in the gateway; this plugin exposes the standard SF "
        "backend routes and browser OAuth proxy. Separate from aigw-gemini-backend "
        "so users can compare/migrate."
    )
    tags: list[str] = ["product:antigravity"]
    backend_call_paths: list[str] = ["/antigravity"]
    # No conflict with aigw-gemini-backend: distinct provider + path.
    conflicts: list[str] = []
    gateway_provider = "antigravity"
    # OAuth-only for v1 (matches the AIGateway provider's supports_api_key=False),
    # so Desktop does not offer a dead-end API-key UI.
    supports_api_key = False
    settings_class = AigwAntigravityBackendSettings
    schema_link_base = "/antigravity/"
    create_router = staticmethod(create_router)
