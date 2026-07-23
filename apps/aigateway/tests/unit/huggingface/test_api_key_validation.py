from __future__ import annotations

import json
from collections.abc import Iterable

import httpx
import pytest

from aigateway.core.api_key_validation import (
    ApiKeyValidationStage,
    ApiKeyValidationState,
)
from aigateway.plugins.huggingface_provider.api_key_validation import HuggingFaceApiKeyValidator
from aigateway.plugins.huggingface_provider.settings import HuggingFacePluginSettings

_KEY = "hf_synthetic_validation_secret"


def _validator(
    responses: Iterable[httpx.Response],
    *,
    settings: HuggingFacePluginSettings | None = None,
) -> tuple[HuggingFaceApiKeyValidator, list[httpx.Request]]:
    queued = list(responses)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return queued.pop(0)

    return (
        HuggingFaceApiKeyValidator(
            settings=settings or HuggingFacePluginSettings(),
            transport=httpx.MockTransport(handler),
        ),
        requests,
    )


@pytest.mark.asyncio
async def test_huggingface_validation_requires_identity_and_readiness() -> None:
    settings = HuggingFacePluginSettings(router_api_base="https://attacker.invalid/v1")
    validator, requests = _validator(
        [
            httpx.Response(200, json={"name": "test-user", "auth": {"type": "access_token"}}),
            httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
        ],
        settings=settings,
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert result.stage is ApiKeyValidationStage.READINESS
    assert result.probe_model == "huggingface/openai/gpt-oss-120b:cerebras"
    assert str(requests[0].url) == "https://huggingface.co/api/whoami-v2"
    assert str(requests[1].url) == "https://router.huggingface.co/v1/chat/completions"
    assert all(request.headers["authorization"] == f"Bearer {_KEY}" for request in requests)
    assert json.loads(requests[1].content) == {
        "model": "openai/gpt-oss-120b:cerebras",
        "max_tokens": 1,
        "stream": False,
        "messages": [{"role": "user", "content": "ping"}],
    }


@pytest.mark.parametrize(
    ("stage", "status", "state"),
    [
        (ApiKeyValidationStage.AUTHENTICATION, 401, ApiKeyValidationState.INVALID),
        (ApiKeyValidationStage.AUTHENTICATION, 402, ApiKeyValidationState.NO_QUOTA),
        (ApiKeyValidationStage.AUTHENTICATION, 403, ApiKeyValidationState.PERMISSION_DENIED),
        (ApiKeyValidationStage.AUTHENTICATION, 429, ApiKeyValidationState.RATE_LIMITED),
        (ApiKeyValidationStage.AUTHENTICATION, 503, ApiKeyValidationState.UNAVAILABLE),
        (ApiKeyValidationStage.READINESS, 401, ApiKeyValidationState.PERMISSION_DENIED),
        (ApiKeyValidationStage.READINESS, 402, ApiKeyValidationState.NO_QUOTA),
        (ApiKeyValidationStage.READINESS, 403, ApiKeyValidationState.PERMISSION_DENIED),
        (ApiKeyValidationStage.READINESS, 429, ApiKeyValidationState.RATE_LIMITED),
        (ApiKeyValidationStage.READINESS, 503, ApiKeyValidationState.UNAVAILABLE),
    ],
)
@pytest.mark.asyncio
async def test_huggingface_classifies_status_by_stage(
    stage: ApiKeyValidationStage,
    status: int,
    state: ApiKeyValidationState,
) -> None:
    responses = []
    if stage is ApiKeyValidationStage.READINESS:
        responses.append(
            httpx.Response(200, json={"name": "test-user", "auth": {"type": "access_token"}})
        )
    responses.append(httpx.Response(status, headers={"retry-after": "13"}, json={"error": _KEY}))
    validator, requests = _validator(responses)

    result = await validator.validate(_KEY)

    assert result.state is state
    assert result.stage is stage
    assert result.retry_after_seconds == (
        13 if state is ApiKeyValidationState.RATE_LIMITED else None
    )
    assert len(requests) == (2 if stage is ApiKeyValidationStage.READINESS else 1)
    assert _KEY not in repr(result)


@pytest.mark.parametrize("payload", [{}, {"name": ""}, {"name": "user", "auth": None}])
@pytest.mark.asyncio
async def test_huggingface_rejects_malformed_identity(payload: dict) -> None:
    validator, requests = _validator([httpx.Response(200, json=payload)])

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is ApiKeyValidationStage.AUTHENTICATION
    assert len(requests) == 1


@pytest.mark.parametrize("name", [1, True, {"value": "user"}, ["user"]])
@pytest.mark.asyncio
async def test_huggingface_rejects_non_string_identity_name(name: object) -> None:
    validator, requests = _validator(
        [
            httpx.Response(200, json={"name": name, "auth": {}}),
            httpx.Response(200, json={"choices": [{}]}),
        ]
    )

    result = await validator.validate(_KEY)

    # INVARIANT: malformed identity metadata cannot advance to the readiness probe.
    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is ApiKeyValidationStage.AUTHENTICATION
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_huggingface_custom_registered_validation_model() -> None:
    settings = HuggingFacePluginSettings(
        default_models=["huggingface/org/model:provider"],
        validation_model="huggingface/org/model:provider",
    )
    validator, requests = _validator(
        [
            httpx.Response(200, json={"name": "user", "auth": {}}),
            httpx.Response(200, json={"choices": [{}]}),
        ],
        settings=settings,
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert result.probe_model == "huggingface/org/model:provider"
    assert json.loads(requests[1].content)["model"] == "org/model:provider"


@pytest.mark.parametrize(
    "settings",
    [
        HuggingFacePluginSettings(default_models=[]),
        HuggingFacePluginSettings(validation_model="huggingface/missing/model"),
    ],
)
@pytest.mark.asyncio
async def test_huggingface_invalid_model_selection_is_local_misconfiguration(
    settings: HuggingFacePluginSettings,
) -> None:
    validator, requests = _validator([], settings=settings)

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.MISCONFIGURED
    assert result.stage is None
    assert requests == []


@pytest.mark.asyncio
async def test_huggingface_rejects_malformed_readiness_success() -> None:
    validator, _requests = _validator(
        [
            httpx.Response(200, json={"name": "user", "auth": {}}),
            httpx.Response(200, json={"choices": []}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is ApiKeyValidationStage.READINESS
