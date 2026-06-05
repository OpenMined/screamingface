from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from aigateway.core.plugin_base import ModelEntry, PluginSettings


def _default_scopes() -> list[str]:
    return [
        "user:profile",
        "user:inference",
        "user:sessions:claude_code",
        "user:mcp_servers",
        "user:file_upload",
    ]


def _default_models() -> list[ModelEntry]:
    return [
        ModelEntry(
            model_name="claude-sonnet-4-5",
            litellm_params={"model": "anthropic/claude-sonnet-4-5"},
        ),
        ModelEntry(
            model_name="claude-opus-4-7",
            litellm_params={"model": "anthropic/claude-opus-4-7"},
        ),
        ModelEntry(
            model_name="claude-haiku-4-5",
            litellm_params={"model": "anthropic/claude-haiku-4-5"},
        ),
    ]


class AnthropicPluginSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGW_ANTHROPIC_",
        extra="ignore",
        populate_by_name=True,
    )

    # Claude subscription login, not the platform/console API-key OAuth entrypoint.
    authorize_url: str = "https://claude.com/cai/oauth/authorize"
    # Verified from Claude Code's public OAuth client flow.
    token_url: str = "https://platform.claude.com/v1/oauth/token"
    client_id: str = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    # Claude subscription tokens carry user scopes; org:create_api_key routes to Console billing.
    scopes: list[str] = Field(default_factory=_default_scopes)
    refresh_scopes: list[str] = Field(default_factory=_default_scopes)
    redirect_path: str = "/callback"
    # Required by the Claude Code OAuth app to show the user-consent screen.
    authorize_extra_params: dict[str, str] = Field(default_factory=lambda: {"code": "true"})

    api_version: str = "2023-06-01"
    beta: str = ",".join(
        [
            "claude-code-20250219",
            "oauth-2025-04-20",
            "interleaved-thinking-2025-05-14",
            "prompt-caching-scope-2026-01-05",
        ]
    )

    models: list[ModelEntry] = Field(default_factory=_default_models)

    claude_code_keychain_service: str = "Claude Code-credentials"
    keychain_account: str = "default"
    bootstrap_user: str = Field(default_factory=lambda: os.environ.get("USER", ""))
