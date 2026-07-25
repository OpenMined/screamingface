from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

_USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"


def _validate_password_bytes(value: SecretStr) -> SecretStr:
    size = len(value.get_secret_value().encode("utf-8"))
    if not 8 <= size <= 72:
        raise ValueError("password must be 8-72 UTF-8 bytes")
    return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=_USERNAME_PATTERN)
    password: SecretStr

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: SecretStr) -> SecretStr:
        return _validate_password_bytes(value)


class CreateAccountRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=_USERNAME_PATTERN)
    password: SecretStr
    display_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: SecretStr) -> SecretStr:
        return _validate_password_bytes(value)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str | None = None
    email: str | None = None
    created_at: datetime
    last_login_at: datetime | None = None
    is_active: bool


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    account: AccountOut
