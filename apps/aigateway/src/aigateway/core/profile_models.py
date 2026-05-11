from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


def profile_id_for(account_id: str, provider: str, name: str) -> str:
    return f"{account_id}:{provider}:{name}"


def credential_name_for(account_id: str, name: str) -> str:
    return f"{account_id}:{name}"


class ProfileState(str, Enum):  # noqa: UP042 - keep tuple-base for pydantic-v1 compat
    PENDING = "pending"
    AUTHENTICATED = "authenticated"
    ERROR = "error"


class ProfileDefaults(BaseModel):
    """Per-profile fallback values applied when the chat body omits a field."""

    model: str | None = None
    system_prompt: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    timeout_seconds: float | None = None
    reasoning_effort: str | None = None  # "low" | "medium" | "high"


class Profile(BaseModel):
    id: str  # f"{account_id}:{provider}:{name}"
    account_id: str = ""
    provider: str
    name: str
    account_label: str | None = None
    scopes: list[str] = Field(default_factory=list)
    last_refreshed_at: datetime | None = None
    state: ProfileState = ProfileState.PENDING
    defaults: ProfileDefaults = Field(default_factory=ProfileDefaults)


class ProfileIndex(BaseModel):
    version: int = 1
    profiles: list[Profile] = Field(default_factory=list)
