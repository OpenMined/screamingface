"""aigw-claude-backend plugin — Claude served via the local AI Gateway.

Same shape as claude_backend_api but the heavy lifting (provider
adapter, OAuth, refresh) lives in apps/aigateway/. This plugin only
configures which model strings to default to and which gateway profile
to authenticate as.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugins.aigw_base import (
    AigwBackendApiPluginBase,
    AigwBackendApiSettingsBase,
)
from screamingface.plugins.aigw_claude_backend.routes import create_router

if TYPE_CHECKING:
    pass


class AigwClaudeBackendSettings(AigwBackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_CLAUDE_BACKEND__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default="anthropic/claude-sonnet-4-5",
        description=(
            "Default Claude model. The gateway routes by the prefix; "
            "must start with 'anthropic/'."
        ),
    )


class AigwClaudeBackendPlugin(AigwBackendApiPluginBase):
    name = "aigw-claude-backend"
    description = (
        "Claude routed through the local AI Gateway (apps/aigateway/). "
        "Drop-in alternative to claude-backend-api: same /aigw-claude routes, "
        "but auth + refresh + adapter live in the gateway, and multiple "
        "OAuth profiles are supported via the gateway's X-Profile header."
    )
    backend_call_paths: list[str] = ["/aigw-claude"]
    settings_class = AigwClaudeBackendSettings
    schema_link_base = "/aigw-claude/"
    create_router = staticmethod(create_router)
