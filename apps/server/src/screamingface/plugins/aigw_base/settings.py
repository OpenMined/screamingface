"""Settings base for aigw_*_backend plugins.

Inherits the standard backend-api settings (default_model, timeout_seconds,
profiles, default_profile, etc.) and adds gateway-specific fields:
the gateway URL and the auth profile to send via X-Profile.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.backend_api_base.plugin_base import BackendApiSettingsBase


class AigwBackendApiSettingsBase(BackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW__",
        env_nested_delimiter="__",
    )

    gateway_url: str = Field(
        default="http://127.0.0.1:9105",
        description="Base URL of the local AI Gateway service.",
    )
    auth_profile: str = Field(
        default="default",
        description="Profile name sent in the X-Profile header on every gateway request.",
    )
