from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ApiKeyValidationState(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    NO_QUOTA = "no_quota"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    MISCONFIGURED = "misconfigured"


class ApiKeyValidationStage(StrEnum):
    AUTHENTICATION = "authentication"
    READINESS = "readiness"


_MESSAGES = {
    ApiKeyValidationState.VALID: "API key is valid and ready for inference.",
    ApiKeyValidationState.INVALID: "The provider rejected this API key. Check or replace it.",
    ApiKeyValidationState.EXPIRED: "This API key has expired. Create a new key.",
    ApiKeyValidationState.NO_QUOTA: (
        "This API key has no available credits or spending limit. Add credits or raise its limit."
    ),
    ApiKeyValidationState.PERMISSION_DENIED: (
        "The API key is valid but cannot use the validation model."
    ),
    ApiKeyValidationState.RATE_LIMITED: ("The provider rate-limited validation. Try again later."),
    ApiKeyValidationState.UNAVAILABLE: (
        "The provider could not complete validation. Try again later."
    ),
    ApiKeyValidationState.MISCONFIGURED: (
        "API-key validation is not configured for this provider. Contact the gateway operator."
    ),
}

_RETRYABLE_STATES = frozenset(
    {
        ApiKeyValidationState.RATE_LIMITED,
        ApiKeyValidationState.UNAVAILABLE,
    }
)


@dataclass(frozen=True, slots=True)
class ApiKeyValidationResult:
    state: ApiKeyValidationState
    stage: ApiKeyValidationStage | None = None
    retry_after_seconds: int | None = None
    probe_model: str | None = None

    @property
    def retryable(self) -> bool:
        return self.state in _RETRYABLE_STATES


class ApiKeyValidator(Protocol):
    async def validate(self, api_key: str) -> ApiKeyValidationResult: ...


def api_key_validation_message(state: ApiKeyValidationState) -> str:
    """Return stable gateway-authored copy; provider text never enters the public contract."""
    return _MESSAGES[state]
