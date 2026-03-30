"""Core session types — canonical message format and storage contract.

These are the shared types that all session-related plugins depend on:
- CanonicalMessage / content blocks — provider-agnostic message format
- SessionMetadata — session envelope
- SessionStore ABC — storage backend contract

Concrete storage backends (FileSessionStore, database, Redis) and
provider adapters live in plugins.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Canonical content blocks (provider-agnostic)
# ---------------------------------------------------------------------------


class TextContent(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["text"] = "text"
    text: str
    cache_hint: str | None = None


class ImageContent(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["image"] = "image"
    media_type: str
    data: str  # base64-encoded


class ToolUseContent(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["tool_use"] = "tool_use"
    tool_use_id: str
    name: str
    input: dict[str, Any]


class ToolResultContent(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[dict[str, Any]]
    is_error: bool | None = None


class ThinkingContent(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: str | None = None


CanonicalContentBlock = Annotated[
    TextContent | ImageContent | ToolUseContent | ToolResultContent | ThinkingContent,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Canonical message
# ---------------------------------------------------------------------------


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class CanonicalMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=_uuid)
    role: Literal["user", "assistant", "system", "tool"]
    content: list[CanonicalContentBlock]
    timestamp: datetime = Field(default_factory=_now)
    provider: str = ""
    model: str | None = None
    token_count: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------


SessionDataT = TypeVar("SessionDataT", bound=BaseModel, default=BaseModel)


class SessionMetadata(BaseModel, Generic[SessionDataT]):
    """Generic session envelope — tool-agnostic base.

    The ``data`` field holds provider-specific payload typed by the
    generic parameter.  For example, Claude sessions use
    ``SessionMetadata[ClaudeSessionData]`` while the storage layer
    works with ``SessionMetadata[Any]``.

    ``extra="allow"`` ensures unknown fields round-trip through storage.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=_uuid)
    provider: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    title: str | None = None
    message_count: int = 0
    tags: list[str] = Field(default_factory=list)
    data: SessionDataT | None = None


# ---------------------------------------------------------------------------
# SessionStore ABC
# ---------------------------------------------------------------------------


class SessionStore(ABC):
    """Abstract base for session storage backends."""

    @abstractmethod
    def create(self, metadata: SessionMetadata) -> str:
        """Persist a new session. Returns the session ID."""

    @abstractmethod
    def load_metadata(self, session_id: str) -> SessionMetadata:
        """Load session metadata. Raises FileNotFoundError if missing."""

    @abstractmethod
    def load_messages(self, session_id: str) -> list[CanonicalMessage]:
        """Load all messages for a session."""

    @abstractmethod
    def append_message(self, session_id: str, message: CanonicalMessage) -> None:
        """Append a message to a session."""

    @abstractmethod
    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[SessionMetadata]:
        """List sessions, most recently updated first."""

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Delete a session. Raises FileNotFoundError if missing."""

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        """Check whether a session exists."""
