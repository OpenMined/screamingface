from __future__ import annotations

import httpx

from aigateway.core.api_key_validation import (
    ApiKeyValidationResult,
    ApiKeyValidationStage,
    ApiKeyValidationState,
)
from aigateway.core.api_key_validation_http import (
    ApiKeyValidationTransportError,
    BoundedJsonResponse,
    ValidationHttpSession,
)

from .settings import OpenAIPluginSettings

_API_BASE = "https://api.openai.com/v1"
# WHY: OpenAI rejects 1 with HTTP 400 for gpt-5-nano; 16 is the live-verified bounded budget that
# returns a structurally valid length-limited Chat Completions response.
_READINESS_MAX_COMPLETION_TOKENS = 16

# Every actionable row needs all three pieces of upstream evidence. The invalid-key row was
# captured with a synthetic key on 2026-08-17; the billing rows are the exact codes in OpenAI's
# current error guide, which also documents `insufficient_quota` as their broader type.
_ACTIONABLE_ERROR_EVIDENCE: dict[
    tuple[ApiKeyValidationStage, int, str, str], ApiKeyValidationState
] = {
    (
        ApiKeyValidationStage.AUTHENTICATION,
        401,
        "invalid_request_error",
        "invalid_api_key",
    ): ApiKeyValidationState.INVALID,
    (
        ApiKeyValidationStage.READINESS,
        401,
        "invalid_request_error",
        "invalid_api_key",
    ): ApiKeyValidationState.INVALID,
    **{
        (ApiKeyValidationStage.READINESS, 429, "insufficient_quota", code): (
            ApiKeyValidationState.NO_QUOTA
        )
        for code in (
            "credit_balance_exhausted",
            "organization_spend_limit_exceeded",
            "project_spend_limit_exceeded",
            "organization_usage_limit_exceeded",
        )
    },
}

# These public states deliberately have no actionable OpenAI tuple yet. Keeping them explicit
# makes the finite table total without promoting guessed values; unknown tuples stay unavailable.
_UNPROMOTED_STATES = frozenset(
    {
        ApiKeyValidationState.EXPIRED,
        ApiKeyValidationState.PERMISSION_DENIED,
        ApiKeyValidationState.RATE_LIMITED,
    }
)
assert set(ApiKeyValidationState) == set(_ACTIONABLE_ERROR_EVIDENCE.values()) | set(
    _UNPROMOTED_STATES
) | {
    ApiKeyValidationState.VALID,
    ApiKeyValidationState.UNAVAILABLE,
    ApiKeyValidationState.MISCONFIGURED,
}


def _result(
    state: ApiKeyValidationState,
    stage: ApiKeyValidationStage | None,
    *,
    response: BoundedJsonResponse | None = None,
    probe_model: str | None = None,
) -> ApiKeyValidationResult:
    retry_after = None
    if state is ApiKeyValidationState.RATE_LIMITED and response is not None:
        retry_after = response.retry_after_seconds
    return ApiKeyValidationResult(
        state=state,
        stage=stage,
        retry_after_seconds=retry_after,
        probe_model=probe_model,
    )


def _classify(
    response: BoundedJsonResponse,
    stage: ApiKeyValidationStage,
    probe_model: str,
) -> ApiKeyValidationResult:
    payload = response.payload
    if response.status_code == 200:
        if not isinstance(payload, dict):
            success = False
        elif isinstance(payload.get("error"), dict):
            success = False
        elif stage is ApiKeyValidationStage.AUTHENTICATION:
            success = payload.get("object") == "list" and isinstance(payload.get("data"), list)
        else:
            choices = payload.get("choices")
            success = (
                isinstance(choices, list)
                and bool(choices)
                and all(
                    isinstance(choice, dict)
                    and "error" not in choice
                    and isinstance(choice.get("message"), dict)
                    and choice["message"].get("role") == "assistant"
                    and isinstance(choice["message"].get("content"), str)
                    for choice in choices
                )
            )
        return _result(
            ApiKeyValidationState.VALID if success else ApiKeyValidationState.UNAVAILABLE,
            stage,
            probe_model=probe_model,
        )

    error = payload.get("error") if isinstance(payload, dict) else None
    raw_type = error.get("type") if isinstance(error, dict) else None
    raw_code = error.get("code") if isinstance(error, dict) else None
    error_type = raw_type if isinstance(raw_type, str) else None
    error_code = raw_code if isinstance(raw_code, str) else None
    state = None
    if error_type is not None and error_code is not None:
        state = _ACTIONABLE_ERROR_EVIDENCE.get(
            (stage, response.status_code, error_type, error_code)
        )
    return _result(
        state or ApiKeyValidationState.UNAVAILABLE,
        stage,
        response=response,
        probe_model=probe_model,
    )


def _effective_model(settings: OpenAIPluginSettings) -> tuple[str, str] | None:
    selected = settings.validation_model
    if selected not in settings.default_models or not selected.startswith("openai/"):
        return None
    upstream = selected.removeprefix("openai/")
    if not upstream or "/" in upstream:
        return None
    return selected, upstream


class OpenAIApiKeyValidator:
    def __init__(
        self,
        *,
        settings: OpenAIPluginSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def validate(self, api_key: str) -> ApiKeyValidationResult:
        model = _effective_model(self._settings)
        if model is None:
            return _result(ApiKeyValidationState.MISCONFIGURED, None)
        probe_model, upstream_model = model
        headers = {"Authorization": f"Bearer {api_key}"}

        async with ValidationHttpSession(transport=self._transport) as session:
            try:
                auth_response = await session.request_json(
                    "GET",
                    f"{_API_BASE}/models",
                    headers=headers,
                )
            except ApiKeyValidationTransportError:
                return _result(
                    ApiKeyValidationState.UNAVAILABLE,
                    ApiKeyValidationStage.AUTHENTICATION,
                    probe_model=probe_model,
                )
            auth_result = _classify(
                auth_response,
                ApiKeyValidationStage.AUTHENTICATION,
                probe_model,
            )
            if auth_result.state is not ApiKeyValidationState.VALID:
                return auth_result

            try:
                readiness_response = await session.request_json(
                    "POST",
                    f"{_API_BASE}/chat/completions",
                    headers=headers,
                    json_body={
                        "model": upstream_model,
                        "max_completion_tokens": _READINESS_MAX_COMPLETION_TOKENS,
                        "stream": False,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
            except ApiKeyValidationTransportError:
                return _result(
                    ApiKeyValidationState.UNAVAILABLE,
                    ApiKeyValidationStage.READINESS,
                    probe_model=probe_model,
                )
            return _classify(
                readiness_response,
                ApiKeyValidationStage.READINESS,
                probe_model,
            )
