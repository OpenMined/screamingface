from __future__ import annotations

from typing import Protocol

from .api_key_validation import (
    ApiKeyValidationResult,
    ApiKeyValidationStage,
    ApiKeyValidationState,
    ApiKeyValidator,
)


class SupportsApiKeyValidation(Protocol):
    def api_key_validator(self) -> ApiKeyValidator | None: ...


class ApiKeyValidationService:
    async def validate(
        self,
        plugin: SupportsApiKeyValidation,
        _provider: str,
        api_key: str,
    ) -> ApiKeyValidationResult | None:
        validator = plugin.api_key_validator()
        if validator is None:
            return None
        result = await validator.validate(api_key)
        # INVARIANT: a provider plugin cannot authorize persistence after auth alone.
        if (
            result.state is ApiKeyValidationState.VALID
            and result.stage is not ApiKeyValidationStage.READINESS
        ):
            return ApiKeyValidationResult(ApiKeyValidationState.MISCONFIGURED)
        return result
