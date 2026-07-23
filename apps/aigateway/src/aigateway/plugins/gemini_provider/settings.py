from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from aigateway.core.plugin_base import PluginSettings


class GeminiPluginSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGW_GEMINI_",
        extra="ignore",
        populate_by_name=True,
    )

    # WHY: operators retarget the readiness probe to any registered gemini-cli model
    # via AIGW_GEMINI_VALIDATION_MODEL without a code deploy. None means "use the
    # registered stable default"; the validator (_effective_model) owns that fallback
    # and resolves the value only through registered models, so an unregistered
    # selection becomes MISCONFIGURED before any network I/O.
    validation_model: str | None = None
