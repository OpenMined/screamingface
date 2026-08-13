"""Operator settings for the taxonomy feature plugin."""

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["TaxonomyPluginSettings"]


class TaxonomyPluginSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGW_TAXONOMY_",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    # WHY default-on: taxonomy only observes and returns request-local evidence. Unlike
    # the global response cache, enabling it creates no cross-caller data-sharing posture.
    enabled: bool = True
