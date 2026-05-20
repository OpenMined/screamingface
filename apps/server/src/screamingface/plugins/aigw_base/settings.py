"""Settings for AIGateway-backed SF plugins.

``AigwBaseSettings`` owns gateway-instance settings shared by every
gateway-backed provider. ``AigwBackendApiSettingsBase`` keeps provider-local
settings such as model and profile selection.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import PluginSettings
from screamingface.plugins.backend_api_base.plugin_base import BackendApiSettingsBase

AigwMode = Literal["local_managed", "external"]


class AigwBaseSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_BASE__",
        env_nested_delimiter="__",
    )

    mode: AigwMode = Field(
        default="local_managed",
        description=(
            "How SF connects to AIGateway: spawn a local managed gateway or use an external one."
        ),
    )
    gateway_url: str = Field(
        default="http://127.0.0.1:9105",
        description="Base URL of the AIGateway service shared by gateway-backed providers.",
    )


class AigwBackendApiSettingsBase(BackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW__",
        env_nested_delimiter="__",
    )

    gateway_url: str = Field(
        default="http://127.0.0.1:9105",
        description="Deprecated compatibility field; use aigw-base.gateway_url instead.",
    )
    auth_profile: str = Field(
        default="default",
        description="Profile name sent in the X-Profile header on every gateway request.",
    )
