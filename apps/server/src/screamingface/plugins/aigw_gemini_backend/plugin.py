"""aigw-gemini-backend plugin — Gemini served via the local AI Gateway."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.aigw_base import (
    AigwBackendApiPluginBase,
    AigwBackendApiSettingsBase,
)
from screamingface.plugins.aigw_gemini_backend.routes import create_router

_GEMINI_MODEL_SUGGESTIONS = [
    "gemini-cli/gemini-2.5-pro",
    "gemini-cli/gemini-2.5-flash",
    "gemini-cli/gemini-2.5-flash-lite",
    "gemini-cli/gemini-2.0-flash",
]


class AigwGeminiBackendSettings(AigwBackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_GEMINI_BACKEND__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default="gemini-cli/gemini-2.5-flash",
        description=(
            "Default Gemini model. The gateway routes by the prefix; "
            "must start with 'gemini-cli/'. Pick from the dropdown or type a "
            "custom slug if the gateway already supports it."
        ),
        examples=_GEMINI_MODEL_SUGGESTIONS,
    )


class AigwGeminiBackendPlugin(AigwBackendApiPluginBase):
    name = "aigw-gemini-backend"
    description = (
        "Gemini served at /gemini via the local AI Gateway. Auth, refresh, "
        "profile storage, and provider adaptation live in the gateway; this "
        "plugin exposes the standard SF backend routes and browser OAuth proxy."
    )
    tags: list[str] = ["product:gemini"]
    backend_call_paths: list[str] = ["/gemini"]
    conflicts: list[str] = ["gemini-backend-api"]
    gateway_provider = "gemini-cli"
    settings_class = AigwGeminiBackendSettings
    schema_link_base = "/gemini/"
    create_router = staticmethod(create_router)
