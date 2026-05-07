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


# Suggestions for the default_model dropdown. Mirrors the gateway's
# anthropic_provider/models.py registry. RJSF's BaseInputTemplate renders
# a `<datalist>` from `examples`, giving the UI a typeahead dropdown that
# still accepts free-text — useful when a new Anthropic snapshot ships
# before this list is updated.
_CLAUDE_MODEL_SUGGESTIONS = [
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-opus-4-7",
    "anthropic/claude-haiku-4-5",
]


class AigwClaudeBackendSettings(AigwBackendApiSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_CLAUDE_BACKEND__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default="anthropic/claude-sonnet-4-5",
        description=(
            "Default Claude model. The gateway routes by the prefix; "
            "must start with 'anthropic/'. Pick from the dropdown or "
            "type a custom snapshot if the gateway already supports it."
        ),
        examples=_CLAUDE_MODEL_SUGGESTIONS,
    )


class AigwClaudeBackendPlugin(AigwBackendApiPluginBase):
    name = "aigw-claude-backend"
    description = (
        "Claude served at /claude via the local AI Gateway (apps/aigateway/). "
        "Drop-in replacement for claude-backend-api: same routes and url4 "
        "contract, but auth + refresh + adapter live in the gateway, and "
        "multiple OAuth profiles are supported via the gateway's X-Profile "
        "header. Mutually exclusive with claude-backend-api — only one can "
        "own /claude at a time."
    )
    # Categorize under "claude" in the UI (same group as claude-backend-api),
    # not under "aigw" — users think in terms of the upstream model, not the
    # transport layer.
    tags: list[str] = ["product:claude"]
    # Same path as claude-backend-api so url4 specs (e.g. cat-breeds-3sources)
    # work unchanged. The conflict below ensures only one Claude backend is
    # ever active.
    backend_call_paths: list[str] = ["/claude"]
    conflicts: list[str] = ["claude-backend-api"]
    gateway_provider = "anthropic"
    settings_class = AigwClaudeBackendSettings
    schema_link_base = "/claude/"
    create_router = staticmethod(create_router)
