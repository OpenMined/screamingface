from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from aigateway.core.api_key_validation import (
    ApiKeyValidationResult,
    ApiKeyValidationStage,
    ApiKeyValidationState,
    api_key_validation_message,
)
from aigateway.core.plugin_base import ModelEntry, PluginSettings, ProviderPluginBase


@pytest.mark.parametrize(
    ("state", "value", "retryable"),
    [
        (ApiKeyValidationState.VALID, "valid", False),
        (ApiKeyValidationState.INVALID, "invalid", False),
        (ApiKeyValidationState.EXPIRED, "expired", False),
        (ApiKeyValidationState.NO_QUOTA, "no_quota", False),
        (ApiKeyValidationState.PERMISSION_DENIED, "permission_denied", False),
        (ApiKeyValidationState.RATE_LIMITED, "rate_limited", True),
        (ApiKeyValidationState.UNAVAILABLE, "unavailable", True),
        (ApiKeyValidationState.MISCONFIGURED, "misconfigured", False),
    ],
)
def test_validation_states_have_stable_values_and_retryability(
    state: ApiKeyValidationState,
    value: str,
    retryable: bool,
) -> None:
    result = ApiKeyValidationResult(state=state)

    assert state.value == value
    assert result.retryable is retryable


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (ApiKeyValidationState.VALID, "API key is valid and ready for inference."),
        (
            ApiKeyValidationState.INVALID,
            "The provider rejected this API key. Check or replace it.",
        ),
        (ApiKeyValidationState.EXPIRED, "This API key has expired. Create a new key."),
        (
            ApiKeyValidationState.NO_QUOTA,
            "This API key has no available credits or spending limit. "
            "Add credits or raise its limit.",
        ),
        (
            ApiKeyValidationState.PERMISSION_DENIED,
            "The API key is valid but cannot use the validation model.",
        ),
        (
            ApiKeyValidationState.RATE_LIMITED,
            "The provider rate-limited validation. Try again later.",
        ),
        (
            ApiKeyValidationState.UNAVAILABLE,
            "The provider could not complete validation. Try again later.",
        ),
        (
            ApiKeyValidationState.MISCONFIGURED,
            "API-key validation is not configured for this provider. Contact the gateway operator.",
        ),
    ],
)
def test_validation_messages_are_gateway_owned(
    state: ApiKeyValidationState,
    message: str,
) -> None:
    assert api_key_validation_message(state) == message


def test_validation_result_is_immutable() -> None:
    result = ApiKeyValidationResult(
        state=ApiKeyValidationState.RATE_LIMITED,
        stage=ApiKeyValidationStage.AUTHENTICATION,
        retry_after_seconds=60,
        probe_model="provider/model",
    )

    with pytest.raises(FrozenInstanceError):
        setattr(result, "retry_after_seconds", 1)


class _UnsupportedPlugin(ProviderPluginBase[PluginSettings]):
    def register_models(self) -> list[ModelEntry]:
        return []


def test_provider_base_has_no_api_key_validator_by_default() -> None:
    assert _UnsupportedPlugin().api_key_validator() is None
