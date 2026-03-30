"""Claude-specific session data for SessionMetadata[ClaudeSessionData]."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ClaudeSessionData(BaseModel):
    """Provider-specific payload for Claude/Anthropic sessions."""

    model_config = ConfigDict(extra="allow")

    system_prompt: str | None = None
    default_model: str | None = None
    total_tokens: int = 0
    forked_from: str | None = None
    fork_point: int | None = None
