from __future__ import annotations

import json
from collections.abc import Iterable

import httpx
import pytest

from aigateway.core.api_key_validation import (
    ApiKeyValidationStage,
    ApiKeyValidationState,
)
from aigateway.plugins.openrouter_provider.api_key_validation import OpenRouterApiKeyValidator
from aigateway.plugins.openrouter_provider.plugin import OpenRouterProviderPlugin
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_KEY = "sk-or-v1-synthetic-validation-secret"


def _validator(
    responses: Iterable[httpx.Response],
    *,
    settings: OpenRouterPluginSettings | None = None,
) -> tuple[OpenRouterApiKeyValidator, list[httpx.Request]]:
    queued = list(responses)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return queued.pop(0)

    return (
        OpenRouterApiKeyValidator(
            settings=settings or OpenRouterPluginSettings(enabled=True),
            transport=httpx.MockTransport(handler),
        ),
        requests,
    )


@pytest.mark.asyncio
async def test_openrouter_validation_uses_hidden_free_router() -> None:
    settings = OpenRouterPluginSettings(enabled=True)
    validator, requests = _validator(
        [
            httpx.Response(200, json={"data": {"limit_remaining": None, "label": "private"}}),
            httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
        ],
        settings=settings,
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert result.stage is ApiKeyValidationStage.READINESS
    assert result.probe_model == "openrouter/openrouter/free"
    assert "openrouter/openrouter/free" not in settings.default_models
    assert str(requests[0].url) == "https://openrouter.ai/api/v1/key"
    assert str(requests[1].url) == "https://openrouter.ai/api/v1/chat/completions"
    assert all(request.headers["authorization"] == f"Bearer {_KEY}" for request in requests)
    assert json.loads(requests[1].content) == {
        "model": "openrouter/free",
        "max_tokens": 1,
        "stream": False,
        "messages": [{"role": "user", "content": "ping"}],
    }
    assert "private" not in repr(result)


@pytest.mark.asyncio
async def test_openrouter_zero_paid_limit_does_not_block_free_readiness() -> None:
    validator, requests = _validator(
        [
            httpx.Response(200, json={"data": {"limit_remaining": 0}}),
            httpx.Response(200, json={"choices": [{}]}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert len(requests) == 2


@pytest.mark.parametrize(
    ("stage", "status", "state"),
    [
        (ApiKeyValidationStage.AUTHENTICATION, 401, ApiKeyValidationState.INVALID),
        (ApiKeyValidationStage.AUTHENTICATION, 402, ApiKeyValidationState.UNAVAILABLE),
        (ApiKeyValidationStage.AUTHENTICATION, 403, ApiKeyValidationState.PERMISSION_DENIED),
        (ApiKeyValidationStage.AUTHENTICATION, 429, ApiKeyValidationState.RATE_LIMITED),
        (ApiKeyValidationStage.AUTHENTICATION, 503, ApiKeyValidationState.UNAVAILABLE),
        (ApiKeyValidationStage.READINESS, 401, ApiKeyValidationState.INVALID),
        (ApiKeyValidationStage.READINESS, 402, ApiKeyValidationState.NO_QUOTA),
        (ApiKeyValidationStage.READINESS, 403, ApiKeyValidationState.PERMISSION_DENIED),
        (ApiKeyValidationStage.READINESS, 400, ApiKeyValidationState.MISCONFIGURED),
        (ApiKeyValidationStage.READINESS, 404, ApiKeyValidationState.MISCONFIGURED),
        (ApiKeyValidationStage.READINESS, 429, ApiKeyValidationState.RATE_LIMITED),
        (ApiKeyValidationStage.READINESS, 503, ApiKeyValidationState.UNAVAILABLE),
    ],
)
@pytest.mark.asyncio
async def test_openrouter_classifies_http_errors(
    stage: ApiKeyValidationStage,
    status: int,
    state: ApiKeyValidationState,
) -> None:
    responses = []
    if stage is ApiKeyValidationStage.READINESS:
        responses.append(httpx.Response(200, json={"data": {}}))
    responses.append(
        httpx.Response(
            status,
            headers={"retry-after": "17"},
            json={"error": {"code": status, "message": _KEY}},
        )
    )
    validator, requests = _validator(responses)

    result = await validator.validate(_KEY)

    assert result.state is state
    assert result.stage is stage
    assert result.retry_after_seconds == (
        17 if state is ApiKeyValidationState.RATE_LIMITED else None
    )
    assert len(requests) == (2 if stage is ApiKeyValidationStage.READINESS else 1)
    assert _KEY not in repr(result)


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (
            {"code": 429, "metadata": {"error_type": "rate_limit_exceeded"}},
            ApiKeyValidationState.RATE_LIMITED,
        ),
        (
            {"code": 402, "metadata": {"error_type": "payment_required"}},
            ApiKeyValidationState.NO_QUOTA,
        ),
        (
            {"code": 403, "metadata": {"error_type": "permission_denied"}},
            ApiKeyValidationState.PERMISSION_DENIED,
        ),
        ({"code": 503}, ApiKeyValidationState.UNAVAILABLE),
    ],
)
@pytest.mark.asyncio
async def test_openrouter_rejects_embedded_http_200_errors(
    error: dict,
    state: ApiKeyValidationState,
) -> None:
    validator, requests = _validator(
        [
            httpx.Response(200, json={"data": {}}),
            httpx.Response(200, json={"choices": [{"finish_reason": "error", "error": error}]}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is state
    assert result.stage is ApiKeyValidationStage.READINESS
    assert len(requests) == 2


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (
            {"code": 402, "metadata": {"error_type": "payment_required"}},
            ApiKeyValidationState.NO_QUOTA,
        ),
        (
            {"code": 429, "metadata": {"error_type": "rate_limit_exceeded"}},
            ApiKeyValidationState.RATE_LIMITED,
        ),
    ],
)
@pytest.mark.asyncio
async def test_openrouter_rejects_top_level_embedded_http_200_errors(
    error: dict,
    state: ApiKeyValidationState,
) -> None:
    validator, requests = _validator(
        [
            httpx.Response(200, json={"data": {}}),
            httpx.Response(200, json={"error": error, "choices": [{}]}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is state
    assert result.stage is ApiKeyValidationStage.READINESS
    assert len(requests) == 2
    assert _KEY not in repr(result)


@pytest.mark.asyncio
async def test_openrouter_finish_only_error_is_unavailable() -> None:
    validator, _requests = _validator(
        [
            httpx.Response(200, json={"data": {}}),
            httpx.Response(200, json={"choices": [{"finish_reason": "error"}]}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE


@pytest.mark.asyncio
async def test_openrouter_contradictory_embedded_evidence_is_unavailable() -> None:
    validator, _requests = _validator(
        [
            httpx.Response(200, json={"data": {}}),
            httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "error": {
                                "code": 503,
                                "metadata": {"error_type": "permission_denied"},
                            }
                        }
                    ]
                },
            ),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE


@pytest.mark.asyncio
async def test_openrouter_non_actionable_type_overrides_misleading_status() -> None:
    validator, _requests = _validator(
        [
            httpx.Response(200, json={"data": {}}),
            httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "error": {
                                "code": 403,
                                "metadata": {"error_type": "provider_unavailable"},
                            }
                        }
                    ]
                },
            ),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE


@pytest.mark.asyncio
async def test_openrouter_rejects_malformed_readiness_success() -> None:
    validator, _requests = _validator(
        [
            httpx.Response(200, json={"data": {}}),
            httpx.Response(200, json={"choices": []}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is ApiKeyValidationStage.READINESS


@pytest.mark.asyncio
async def test_openrouter_explicit_registered_validation_model() -> None:
    settings = OpenRouterPluginSettings(
        enabled=True,
        validation_model="openrouter/anthropic/claude-fable-5",
    )
    validator, requests = _validator(
        [
            httpx.Response(200, json={"data": {}}),
            httpx.Response(200, json={"choices": [{}]}),
        ],
        settings=settings,
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert json.loads(requests[1].content)["model"] == "anthropic/claude-fable-5"


@pytest.mark.asyncio
async def test_openrouter_explicit_internal_default_is_valid() -> None:
    settings = OpenRouterPluginSettings(
        enabled=True,
        validation_model="openrouter/openrouter/free",
    )
    validator, requests = _validator(
        [
            httpx.Response(200, json={"data": {}}),
            httpx.Response(200, json={"choices": [{}]}),
        ],
        settings=settings,
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert result.probe_model == "openrouter/openrouter/free"
    assert json.loads(requests[1].content)["model"] == "openrouter/free"


@pytest.mark.parametrize(
    "validation_model",
    ["openrouter/missing/model", "bad-model", ""],
)
@pytest.mark.asyncio
async def test_openrouter_explicit_unregistered_model_is_misconfigured(
    validation_model: str,
) -> None:
    settings = OpenRouterPluginSettings(enabled=True, validation_model=validation_model)
    validator, requests = _validator([], settings=settings)

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.MISCONFIGURED
    assert requests == []


def test_disabled_openrouter_has_no_operational_validator() -> None:
    assert (
        OpenRouterProviderPlugin(OpenRouterPluginSettings(enabled=False)).api_key_validator()
        is None
    )
    assert (
        OpenRouterProviderPlugin(OpenRouterPluginSettings(enabled=True)).api_key_validator()
        is not None
    )
