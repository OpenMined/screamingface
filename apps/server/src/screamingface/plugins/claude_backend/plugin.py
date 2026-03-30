"""Claude Backend plugin — REST wrapper for the local Claude Code CLI.

Also serves as the session orchestrator: loads session history from the
session service, translates via ClaudeAdapter, and saves turns after
responses.
"""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.claude.session_adapter import ClaudeAdapter
from screamingface.plugins.claude_backend.models import ClaudeProfile
from screamingface.plugins.claude_backend.routes import create_router

_PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class ClaudeBackendSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_BACKEND__",
        env_nested_delimiter="__",
    )
    default_model: str | None = None
    default_effort: str = "medium"
    timeout_seconds: float = 300.0
    max_budget_usd: float | None = None
    permission_mode: str | None = None
    dangerously_skip_permissions: bool = False
    profiles: dict[str, ClaudeProfile] = Field(
        default_factory=dict,
        description="Named pre-configured Claude execution profiles.",
    )
    default_profile: str | None = Field(
        default=None,
        description="Profile to use when none is specified.",
    )

    @field_validator("profiles")
    @classmethod
    def _validate_profile_keys(cls, v: dict[str, ClaudeProfile]) -> dict[str, ClaudeProfile]:
        for key in v:
            if not _PROFILE_NAME_RE.match(key):
                msg = (
                    f"Invalid profile name {key!r}: must be lowercase alphanumeric, "
                    "hyphens, or underscores, starting with a letter or digit."
                )
                raise ValueError(msg)
        return v


class ClaudeBackendPlugin(Plugin):
    name = "claude-backend"
    description = "REST wrapper for the local Claude Code CLI"
    depends: list[str] = ["claude", "url4-executor"]
    settings_class = ClaudeBackendSettings
    system_deps = ["claude"]

    def __init__(self) -> None:
        self._adapter = ClaudeAdapter(
            api_key_resolver=lambda: os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    def customize_schema(self, schema: dict) -> dict:
        settings: ClaudeBackendSettings = self.settings  # type: ignore[assignment]
        profile_names = list(settings.profiles.keys())
        props = schema.get("properties", {})
        if profile_names and "default_profile" in props:
            props["default_profile"]["enum"] = profile_names
        if "profiles" in props:
            props["profiles"]["x-link-base"] = "/claude/"
        return schema

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        router = create_router(self.settings)  # type: ignore[arg-type]
        routes.add_router(self.name, router, prefix="")

        # Register session orchestration hooks
        hooks.register(
            "session.enrich_request",
            self._enrich_request,
            plugin_name=self.name,
        )
        hooks.register(
            "session.save_response",
            self._save_response,
            plugin_name=self.name,
        )

    # ------------------------------------------------------------------
    # Session orchestration hooks
    # ------------------------------------------------------------------

    async def _enrich_request(
        self,
        *,
        body: dict[str, Any],
        session_id: str,
        session_service_url: str,
    ) -> dict[str, Any] | None:
        """Load session history and prepend to the request body.

        Called by claude_frontend via hook when X-Session-Id is present.
        Returns the enriched body, or None if session loading fails.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{session_service_url}/sessions/{session_id}/messages",
                )
                if resp.status_code == 404:
                    # Auto-create session on first use
                    await client.post(
                        f"{session_service_url}/sessions",
                        params={"title": f"Session {session_id}"},
                    )
                    return body
                resp.raise_for_status()
                history_data = resp.json()

            if not history_data:
                return body

            from screamingface.core.session import CanonicalMessage

            history = [CanonicalMessage.model_validate(m) for m in history_data]
            provider_data = self._adapter.to_provider_messages(history)

            # Prepend history messages before the current turn
            existing_messages = body.get("messages", [])
            body["messages"] = provider_data.get("messages", []) + existing_messages

            # Merge system messages
            history_system = provider_data.get("system")
            if history_system:
                existing_system = body.get("system")
                if existing_system is None:
                    body["system"] = history_system
                elif isinstance(existing_system, str):
                    # Convert to list format for merging
                    body["system"] = history_system + [{"type": "text", "text": existing_system}]
                elif isinstance(existing_system, list):
                    body["system"] = history_system + existing_system

            logger.info(
                "Enriched request with %d history messages for session %s",
                len(provider_data.get("messages", [])),
                session_id,
            )
            return body

        except Exception:
            logger.warning("Failed to enrich request from session %s", session_id, exc_info=True)
            return None

    async def _save_response(
        self,
        *,
        session_id: str,
        session_service_url: str,
        user_message_body: dict[str, Any],
        response_body: dict[str, Any],
    ) -> None:
        """Save the user turn and assistant response to the session service.

        Called by claude_frontend via hook after receiving the response.
        """
        try:
            from screamingface.core.session import (
                CanonicalContentBlock,
                CanonicalMessage,
                TextContent,
            )

            # Build canonical user message from the raw request content
            user_content_raw = user_message_body.get("content", "")
            blocks: list[CanonicalContentBlock] = []
            if isinstance(user_content_raw, str):
                blocks.append(TextContent(text=user_content_raw))
            else:
                for block in user_content_raw:
                    if isinstance(block, dict) and block.get("type") == "text":
                        blocks.append(TextContent(text=block["text"]))
                    elif isinstance(block, dict):
                        blocks.append(TextContent(text=str(block)))
                if not blocks:
                    blocks.append(TextContent(text=str(user_content_raw)))

            user_msg = CanonicalMessage(
                role="user",
                content=blocks,
                provider="anthropic",
            )

            # Parse assistant response via adapter
            assistant_msgs = self._adapter.from_provider_response(response_body)

            async with httpx.AsyncClient(timeout=10) as client:
                # Ensure session exists
                check = await client.get(f"{session_service_url}/sessions/{session_id}")
                if check.status_code == 404:
                    await client.post(
                        f"{session_service_url}/sessions",
                        params={"title": f"Session {session_id}"},
                    )

                # Append user message
                await client.post(
                    f"{session_service_url}/sessions/{session_id}/messages",
                    json=user_msg.model_dump(mode="json"),
                )

                # Append assistant message(s)
                for msg in assistant_msgs:
                    await client.post(
                        f"{session_service_url}/sessions/{session_id}/messages",
                        json=msg.model_dump(mode="json"),
                    )

            logger.info(
                "Saved %d messages to session %s",
                1 + len(assistant_msgs),
                session_id,
            )

        except Exception:
            logger.warning("Failed to save response to session %s", session_id, exc_info=True)
