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
from aigateway.plugins.gemini_provider.api_key_validation import GeminiApiKeyValidator
from aigateway.plugins.gemini_provider.models import MODELS
from aigateway.plugins.gemini_provider.settings import GeminiPluginSettings

_KEY = "AIzaSySyntheticValidationSecret"
_ERROR_INFO = "type.googleapis.com/google.rpc.ErrorInfo"


def _validator(
    responses: Iterable[httpx.Response],
    *,
    models: list[ModelEntry] | None = None,
    settings: GeminiPluginSettings | None = None,
) -> tuple[GeminiApiKeyValidator, list[httpx.Request]]:
    queued = list(responses)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return queued.pop(0)

    return (
        GeminiApiKeyValidator(
            settings=settings or GeminiPluginSettings(validation_model=None),
            registered_models=list(MODELS) if models is None else models,
            transport=httpx.MockTransport(handler),
        ),
        requests,
    )


def _error(
    status: str,
    *,
    reason: str | None = None,
    domain: str = "googleapis.com",
    retry_delay: str | None = None,
) -> dict:
    details: list[dict[str, str]] = []
    if reason is not None:
        details.append({"@type": _ERROR_INFO, "reason": reason, "domain": domain})
    if retry_delay is not None:
        details.append(
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": retry_delay,
            }
        )
    return {"error": {"status": status, "message": _KEY, "details": details}}


@pytest.mark.asyncio
async def test_gemini_validation_requires_both_stages() -> None:
    validator, requests = _validator(
        [
            httpx.Response(200, json={"models": []}),
            httpx.Response(200, json={"candidates": [{"content": {"parts": []}}]}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert result.stage is ApiKeyValidationStage.READINESS
    assert result.probe_model == "gemini-cli/gemini-3.1-flash-lite"
    assert str(requests[0].url) == (
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
    )
    assert str(requests[1].url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.1-flash-lite:generateContent"
    )
    assert requests[0].headers["x-goog-api-key"] == _KEY
    body = json.loads(requests[1].content)
    assert body == {
        "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 1},
    }
    assert "stream" not in body


@pytest.mark.parametrize(
    ("reason", "state"),
    [
        ("API_KEY_INVALID", ApiKeyValidationState.INVALID),
        ("SERVICE_DISABLED", ApiKeyValidationState.PERMISSION_DENIED),
        ("API_KEY_SERVICE_BLOCKED", ApiKeyValidationState.PERMISSION_DENIED),
        ("API_KEY_HTTP_REFERRER_BLOCKED", ApiKeyValidationState.PERMISSION_DENIED),
        ("API_KEY_IP_ADDRESS_BLOCKED", ApiKeyValidationState.PERMISSION_DENIED),
        ("API_KEY_ANDROID_APP_BLOCKED", ApiKeyValidationState.PERMISSION_DENIED),
        ("API_KEY_IOS_APP_BLOCKED", ApiKeyValidationState.PERMISSION_DENIED),
    ],
)
@pytest.mark.asyncio
async def test_gemini_uses_allowlisted_error_info(
    reason: str, state: ApiKeyValidationState
) -> None:
    validator, requests = _validator(
        [httpx.Response(400, json=_error("INVALID_ARGUMENT", reason=reason))]
    )

    result = await validator.validate(_KEY)

    assert result.state is state
    assert result.stage is ApiKeyValidationStage.AUTHENTICATION
    assert len(requests) == 1
    assert _KEY not in repr(result)


@pytest.mark.parametrize(
    "payload",
    [
        _error("INVALID_ARGUMENT", reason="API_KEY_INVALID", domain="attacker.invalid"),
        _error("INVALID_ARGUMENT", reason="UNKNOWN"),
        _error("FAILED_PRECONDITION", reason="API_KEY_INVALID"),
        {"error": {"status": "INVALID_ARGUMENT", "message": "API_KEY_INVALID"}},
    ],
)
@pytest.mark.asyncio
async def test_gemini_does_not_guess_from_partial_evidence(payload: dict) -> None:
    validator, requests = _validator([httpx.Response(400, json=payload)])

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is ApiKeyValidationStage.AUTHENTICATION
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_gemini_resource_exhausted_uses_structured_retry_info() -> None:
    validator, _requests = _validator(
        [
            httpx.Response(
                429,
                headers={"retry-after": "9"},
                json=_error("RESOURCE_EXHAUSTED", retry_delay="3.2s"),
            )
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.RATE_LIMITED
    assert result.retry_after_seconds == 4


@pytest.mark.asyncio
async def test_gemini_structured_permission_denied() -> None:
    validator, _requests = _validator([httpx.Response(403, json=_error("PERMISSION_DENIED"))])

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_gemini_structured_unauthenticated_401_is_invalid() -> None:
    validator, requests = _validator([httpx.Response(401, json=_error("UNAUTHENTICATED"))])

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.INVALID
    assert result.stage is ApiKeyValidationStage.AUTHENTICATION
    assert len(requests) == 1
    assert _KEY not in repr(result)


@pytest.mark.asyncio
async def test_gemini_unstructured_429_is_unavailable() -> None:
    validator, _requests = _validator([httpx.Response(429, json={"error": {}})])

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE


@pytest.mark.asyncio
async def test_gemini_rejects_blocked_reason_on_contradictory_status() -> None:
    validator, _requests = _validator(
        [httpx.Response(503, json=_error("INTERNAL", reason="SERVICE_DISABLED"))]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE


@pytest.mark.asyncio
async def test_gemini_rejects_malformed_readiness_success() -> None:
    validator, _requests = _validator(
        [
            httpx.Response(200, json={"models": []}),
            httpx.Response(200, json={"candidates": []}),
        ]
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert result.stage is ApiKeyValidationStage.READINESS


@pytest.mark.parametrize("payload", [{}, {"models": {}}, {"models": "bad"}])
@pytest.mark.asyncio
async def test_gemini_rejects_malformed_auth_success(payload: dict) -> None:
    validator, requests = _validator([httpx.Response(200, json=payload)])

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.UNAVAILABLE
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_gemini_missing_validation_model_is_local_misconfiguration() -> None:
    validator, requests = _validator([], models=[])

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.MISCONFIGURED
    assert result.stage is None
    assert requests == []


@pytest.mark.asyncio
async def test_gemini_registered_override_resolves_to_that_model() -> None:
    validator, requests = _validator(
        [
            httpx.Response(200, json={"models": []}),
            httpx.Response(200, json={"candidates": [{"content": {"parts": []}}]}),
        ],
        settings=GeminiPluginSettings(validation_model="gemini-cli/gemini-2.5-pro"),
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.VALID
    assert result.probe_model == "gemini-cli/gemini-2.5-pro"
    assert str(requests[1].url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
    )


@pytest.mark.asyncio
async def test_gemini_unregistered_override_is_misconfiguration_without_io() -> None:
    validator, requests = _validator(
        [],
        settings=GeminiPluginSettings(validation_model="gemini-cli/gemini-does-not-exist"),
    )

    result = await validator.validate(_KEY)

    assert result.state is ApiKeyValidationState.MISCONFIGURED
    assert result.stage is None
    assert requests == []
