from __future__ import annotations

import json
from collections.abc import Iterable

import httpx
import pytest

from aigateway.core.api_key_validation import (
    ApiKeyValidationStage,
    ApiKeyValidationState,
)
from aigateway.core.plugin_base import ModelEntry
from aigateway.plugins.anthropic_provider.api_key_validation import AnthropicApiKeyValidator
from aigateway.plugins.anthropic_provider.settings import AnthropicPluginSettings

_KEY = "sk-ant-api03-synthetic-validation-secret"


def _validator(
    responses: Iterable[httpx.Response],
    *,
    settings: AnthropicPluginSettings | None = None,
    models: list[ModelEntry] | None = None,
) -> tuple[AnthropicApiKeyValidator, list[httpx.Request]]:
    queued = list(responses)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return queued.pop(0)

    effective_settings = settings or AnthropicPluginSettings()
    return (
        AnthropicApiKeyValidator(
            settings=effective_settings,
            registered_models=models if models is not None else list(effective_settings.models),
            transport=httpx.MockTransport(handler),
        ),
        requests,
    )


@pytest.mark.asyncio
async def test_anthropic_validation_requires_both_stages() -> None:
    validator, requests = _validator(
        [
            httpx.Response(200, json={"data": []}),
            httpx.Response(200, json={"type": "message", "content": []}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert result.stage is ApiKeyValidationStage.READINESS
    assert result.probe_model == "claude-haiku-4-5"
    assert [request.method for request in requests] == ["GET", "POST"]
    assert str(requests[0].url) == "https://api.anthropic.com/v1/models?limit=1"
    assert str(requests[1].url) == "https://api.anthropic.com/v1/messages"
    assert requests[0].headers["x-api-key"] == _KEY
    assert requests[0].headers["anthropic-version"] == "2023-06-01"
    body = json.loads(requests[1].content)
    assert body == {
        "model": "claude-haiku-4-5",
        "max_tokens": 1,
        "stream": False,
        "messages": [{"role": "user", "content": "ping"}],
    }


@pytest.mark.parametrize(
    ("status", "error_type", "state"),
    [
        (401, "authentication_error", ApiKeyValidationState.INVALID),
        (402, "billing_error", ApiKeyValidationState.NO_QUOTA),
        (403, "permission_error", ApiKeyValidationState.PERMISSION_DENIED),
        (429, "rate_limit_error", ApiKeyValidationState.RATE_LIMITED),
        (529, "overloaded_error", ApiKeyValidationState.UNAVAILABLE),
    ],
)
@pytest.mark.asyncio
async def test_anthropic_auth_failure_is_structured_and_skips_readiness(
    status: int,
    error_type: str,
    state: ApiKeyValidationState,
) -> None:
    validator, requests = _validator(
        [
            httpx.Response(
                status,
                headers={"retry-after": "11"},
                json={"type": "error", "error": {"type": error_type, "message": _KEY}},
            )
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is state
    assert result.stage is ApiKeyValidationStage.AUTHENTICATION
    assert result.retry_after_seconds == (
        11 if state is ApiKeyValidationState.RATE_LIMITED else None
    )
    assert len(requests) == 1
    assert _KEY not in repr(result)


@pytest.mark.asyncio
async def test_anthropic_does_not_guess_from_status_or_prose() -> None:
    validator, requests = _validator(
        [httpx.Response(401, json={"error": {"type": "unknown", "message": "expired"}})]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is ApiKeyValidationStage.AUTHENTICATION
    assert len(requests) == 1


@pytest.mark.parametrize(
    "payload",
    [{}, {"data": {}}, {"data": "not-a-list"}],
)
@pytest.mark.asyncio
async def test_anthropic_rejects_malformed_auth_success(payload: object) -> None:
    validator, requests = _validator([httpx.Response(200, json=payload)])

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is ApiKeyValidationStage.AUTHENTICATION
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_anthropic_validation_model_override_uses_registered_upstream_mapping() -> None:
    models = [
        ModelEntry(model_name="custom-alias", litellm_params={"model": "anthropic/custom-model"})
    ]
    settings = AnthropicPluginSettings(models=models, validation_model="custom-alias")
    validator, requests = _validator(
        [
            httpx.Response(200, json={"data": []}),
            httpx.Response(200, json={"type": "message", "content": []}),
        ],
        settings=settings,
        models=models,
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert result.probe_model == "custom-alias"
    assert json.loads(requests[1].content)["model"] == "custom-model"


@pytest.mark.asyncio
async def test_anthropic_unregistered_validation_model_is_local_misconfiguration() -> None:
    settings = AnthropicPluginSettings(validation_model="missing")
    validator, requests = _validator([], settings=settings)

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.MISCONFIGURED
    assert result.stage is None
    assert requests == []


@pytest.mark.asyncio
async def test_anthropic_rejects_malformed_readiness_success() -> None:
    validator, _requests = _validator(
        [
            httpx.Response(200, json={"data": []}),
            httpx.Response(200, json={"type": "message", "content": {}}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is ApiKeyValidationStage.READINESS


@pytest.mark.parametrize(
    "stage",
    [ApiKeyValidationStage.AUTHENTICATION, ApiKeyValidationStage.READINESS],
)
@pytest.mark.asyncio
async def test_anthropic_invalid_request_does_not_guess_low_credit(
    stage: ApiKeyValidationStage,
) -> None:
    responses = []
    if stage is ApiKeyValidationStage.READINESS:
        responses.append(httpx.Response(200, json={"data": []}))
    responses.append(
        httpx.Response(
            400,
            json={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "credit balance is too low",
                },
            },
        )
    )
    validator, requests = _validator(responses)

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is stage
    assert len(requests) == (1 if stage is ApiKeyValidationStage.AUTHENTICATION else 2)
