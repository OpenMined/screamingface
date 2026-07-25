from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr

PoolAuthType = Literal["api_key"]


class GlobalCredentialPoolResponse(BaseModel):
    id: UUID
    provider: str
    label: str
    auth_type: PoolAuthType
    is_active: bool
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime


class GlobalCredentialPoolListResponse(BaseModel):
    pools: list[GlobalCredentialPoolResponse]


class CreateGlobalCredentialPoolRequest(BaseModel):
    """Provision a shared credential for a provider (api-key only for now).

    OAuth-backed pools are out of scope for this iteration — see
    docs/spec/2026-07-24-aigateway-shared-credential-pools-spec.md.
    """

    model_config = ConfigDict(hide_input_in_errors=True)

    provider: str
    api_key: SecretStr


class PatchGlobalCredentialPoolRequest(BaseModel):
    is_active: bool | None = None
    api_key: SecretStr | None = None
