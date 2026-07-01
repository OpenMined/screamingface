"""aigw-huggingface-backend plugin — Hugging Face served via the local AI Gateway."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.aigw_base import (
    AigwBackendApiPluginBase,
    AigwBackendApiSettingsBase,
)
from screamingface.plugins.aigw_huggingface_backend.routes import create_route_bundle, create_router


class AigwHuggingfaceBackendSettings(AigwBackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_HUGGINGFACE_BACKEND__",
        env_nested_delimiter="__",
    )

    # `default_model` suggestions are derived live from the gateway's /v1/models
    # registry by AigwBackendApiPluginBase.customize_schema (SF-284) — not copied
    # here. Source of truth: apps/aigateway/.../huggingface_provider/settings.py.
    default_model: str | None = Field(
        default="huggingface/deepseek-ai/DeepSeek-R1:novita",
        description=(
            "Default Hugging Face model. The gateway routes by the 'huggingface/' "
            "prefix; use the unified-router form 'huggingface/<org>/<model>:<provider>'. "
            "Pick from the dropdown or type a custom slug the gateway already supports."
        ),
    )


class AigwHuggingfaceBackendPlugin(AigwBackendApiPluginBase):
    name = "aigw-huggingface-backend"
    description = (
        "Hugging Face served at /huggingface via the local AI Gateway. Auth "
        "(API key/PAT), profile storage, and provider adaptation live in the "
        "gateway; this plugin exposes the standard SF backend routes and the "
        "browser-driven API-key connection proxy."
    )
    tags: list[str] = ["product:huggingface"]
    backend_call_paths: list[str] = ["/huggingface"]
    conflicts: list[str] = []
    gateway_provider = "huggingface"
    supports_api_key = True
    # Hugging Face is API-key/PAT only — no browser OAuth. This drives the desktop
    # connection UI to default to (and only offer) the API-key flow; without it the
    # form would default to an OAuth 'Start' the gateway rejects for HF.
    supports_oauth = False
    settings_class = AigwHuggingfaceBackendSettings
    schema_link_base = "/huggingface/"
    create_route_bundle = staticmethod(create_route_bundle)
    create_router = staticmethod(create_router)
