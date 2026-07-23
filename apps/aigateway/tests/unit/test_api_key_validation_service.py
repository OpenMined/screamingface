from __future__ import annotations

from dataclasses import dataclass

import pytest

from aigateway.core.api_key_validation import (
    ApiKeyValidationResult,
    ApiKeyValidationStage,
    ApiKeyValidationState,
    ApiKeyValidator,
)
from aigateway.core.api_key_validation_service import ApiKeyValidationService
from aigateway.plugins.anthropic_provider.api_key_validation import AnthropicApiKeyValidator
from aigateway.plugins.anthropic_provider.plugin import AnthropicProviderPlugin
from aigateway.plugins.gemini_provider.api_key_validation import GeminiApiKeyValidator
from aigateway.plugins.gemini_provider.plugin import GeminiProviderPlugin
from aigateway.plugins.huggingface_provider.api_key_validation import HuggingFaceApiKeyValidator
from aigateway.plugins.huggingface_provider.plugin import HuggingFaceProviderPlugin


class _NoValidatorPlugin:
    def api_key_validator(self):
        return None


@dataclass
class _RecordingValidator:
    keys: list[str]

    async def validate(self, api_key: str) -> ApiKeyValidationResult:
        self.keys.append(api_key)
        return ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
            probe_model="provider/model",
        )


class _Plugin:
    def __init__(self, validator: _RecordingValidator) -> None:
        self.validator = validator
        self.calls = 0

    def api_key_validator(self) -> _RecordingValidator:
        self.calls += 1
        return self.validator


@dataclass
class _StaticValidator:
    result: ApiKeyValidationResult

    async def validate(self, api_key: str) -> ApiKeyValidationResult:
        del api_key
        return self.result


class _StaticPlugin:
    def __init__(self, result: ApiKeyValidationResult) -> None:
        self.validator = _StaticValidator(result)

    def api_key_validator(self) -> ApiKeyValidator:
        return self.validator


@pytest.mark.asyncio
async def test_service_returns_none_without_operational_validator() -> None:
    result = await ApiKeyValidationService().validate(
        _NoValidatorPlugin(),
        "unsupported",
        "synthetic-secret",
    )

    assert result is None


@pytest.mark.asyncio
async def test_service_resolves_validator_once_and_forwards_key() -> None:
    validator = _RecordingValidator(keys=[])
    plugin = _Plugin(validator)

    result = await ApiKeyValidationService().validate(
        plugin,
        "provider",
        "synthetic-secret",
    )

    assert result == ApiKeyValidationResult(
        state=ApiKeyValidationState.VALID,
        stage=ApiKeyValidationStage.READINESS,
        probe_model="provider/model",
    )
    assert plugin.calls == 1
    assert validator.keys == ["synthetic-secret"]


@pytest.mark.parametrize("stage", [None, ApiKeyValidationStage.AUTHENTICATION])
@pytest.mark.asyncio
async def test_service_rejects_valid_without_readiness(
    stage: ApiKeyValidationStage | None,
) -> None:
    result = await ApiKeyValidationService().validate(
        _StaticPlugin(ApiKeyValidationResult(ApiKeyValidationState.VALID, stage=stage)),
        "provider",
        "synthetic-secret",
    )

    # INVARIANT: no plugin can authorize persistence without completing readiness.
    assert result == ApiKeyValidationResult(ApiKeyValidationState.MISCONFIGURED)


@pytest.mark.parametrize(
    ("plugin", "validator_type"),
    [
        (AnthropicProviderPlugin(), AnthropicApiKeyValidator),
        (GeminiProviderPlugin(), GeminiApiKeyValidator),
        (HuggingFaceProviderPlugin(), HuggingFaceApiKeyValidator),
    ],
)
def test_builtin_plugins_expose_their_operational_validator(plugin, validator_type) -> None:
    assert isinstance(plugin.api_key_validator(), validator_type)
