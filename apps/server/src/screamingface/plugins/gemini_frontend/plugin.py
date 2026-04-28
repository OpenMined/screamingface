"""Gemini Frontend plugin — transparent proxy on a dedicated port.

Proxies the Google AI Gemini API. Most behavior lives in
:class:`frontend_base.FrontendPluginBase`; this module declares the
Gemini-specific overrides only.
"""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from screamingface.plugins.frontend_base import (
    FrontendPluginBase,
    FrontendSettingsBase,
)
from screamingface.plugins.gemini_frontend.proxy import create_router


class GeminiFrontendSettings(FrontendSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_GEMINI_FRONTEND__",
        env_nested_delimiter="__",
    )

    upstream_url: str = "https://generativelanguage.googleapis.com"
    listen_port: int = 9103
    default_backend_path: str = "/gemini"


class GeminiFrontendPlugin(FrontendPluginBase):
    name = "gemini-frontend"
    description = "Transparent proxy between Gemini CLI and the Google AI API"
    tags: list[str] = ["product:gemini"]
    depends: list[str] = ["url4-specs", "url4-executor", "frontend-base"]
    settings_class = GeminiFrontendSettings

    cli_binary = "gemini"
    cli_install_hint = (
        "Install it with: npm install -g @anthropic-ai/gemini-cli "
        "or see https://github.com/anthropics/gemini-cli"
    )
    app_title = "gemini-frontend"
    create_router = staticmethod(create_router)
