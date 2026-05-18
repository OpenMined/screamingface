from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .identity import AccountIdentity

OAuthConnectionStatus = Literal["pending", "active", "expired", "revoked", "error"]


class OAuthConnectionResponse(BaseModel):
    id: UUID
    account_id: UUID
    provider: str
    label: str
    status: OAuthConnectionStatus
    account: AccountIdentity | None = None
    credential_locator: dict[str, Any]
    created_at: datetime
    last_used_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    error_message: str | None = None
    is_duplicate: bool = False


class OAuthConnectionListResponse(BaseModel):
    connections: list[OAuthConnectionResponse] = Field(default_factory=list)


class CreateOAuthConnectionRequest(BaseModel):
    provider: str
    label: str | None = None


class PatchOAuthConnectionRequest(BaseModel):
    label: str | None = None


class StartOAuthConnectionResponse(BaseModel):
    connection_id: UUID
    authorize_url: str
    state: str
    expires_in: int = 600
