"""gemini-backend-api plugin — Google AI Gemini API implementation.

Most behavior lives in :class:`backend_api_base.BackendApiPluginBase`.
This module declares Gemini-specific settings (fallback chain + 429
wait cap) and overrides only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.backend_api_base import (
    BackendApiPluginBase,
    BackendApiSettingsBase,
)
from screamingface.plugins.gemini_backend_api.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI


class GeminiBackendApiSettings(BackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_GEMINI_BACKEND_API__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default=None,
        description="Default Gemini model. Falls back to 'gemini-2.5-flash'.",
    )
    fallback_models: list[str] = Field(
        default_factory=lambda: ["gemini-2.5-pro", "gemini-2.5-flash-lite"],
        description=(
            "Fallback chain when the configured model returns "
            "QUOTA_EXHAUSTED 429. Each model has its own quota bucket "
            "on Code Assist, so flash → pro → flash-lite usually "
            "self-heals during a single-model burnout. Empty list "
            "disables fallback."
        ),
    )
    max_total_429_wait_seconds: float = Field(
        default=30.0,
        description=(
            "Cap on cumulative sleep across 429 retries within a single "
            "request. Past this budget the backend raises BackendError(429) "
            "instead of continuing to obey provider retry-after, so request-"
            "level timeouts (e.g. 45s in tests) surface a clean error rather "
            "than an httpx ReadTimeout."
        ),
    )


class GeminiBackendApiPlugin(BackendApiPluginBase):
    name = "gemini-backend-api"
    description = "Direct Google AI Gemini API backend for ensemble fan-out"
    tags: list[str] = ["product:gemini"]
    depends: list[str] = ["llm-base", "backend-api-base"]
    conflicts: list[str] = ["aigw-gemini-backend"]
    backend_call_paths: list[str] = ["/gemini"]
    cli_auth_command = "gemini auth login"
    backend_status_help = {
        "rate_limited": "Gemini API rate limit reached. Capacity will reset automatically.",
        "reauth": (
            "Gemini OAuth token is missing or has insufficient API scopes. "
            "Click Re-authenticate to run 'gemini auth login'."
        ),
        "degraded": "Gemini backend is available but experiencing issues.",
    }
    settings_class = GeminiBackendApiSettings

    schema_link_base = "/gemini/"
    create_router = staticmethod(create_router)

    def _make_interpreter(self, app: FastAPI):
        from screamingface.plugins.gemini_backend_api.interpreter import (
            GeminiBackendApiInterpreter,
        )

        return GeminiBackendApiInterpreter(
            app=app,
            settings=self.settings,  # type: ignore[arg-type]
        )
