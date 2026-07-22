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
from aigateway.core.plugin_base import ModelEntry

from .settings import AnthropicPluginSettings

_API_BASE = "https://api.anthropic.com/v1"
_PREFERRED_MODEL = "claude-haiku-4-5"


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
            return _result(ApiKeyValidationState.UNAVAILABLE, stage, probe_model=probe_model)
        if stage is ApiKeyValidationStage.AUTHENTICATION:
            success = isinstance(payload.get("data"), list)
        else:
            success = payload.get("type") == "message" and isinstance(payload.get("content"), list)
        return _result(
            ApiKeyValidationState.VALID if success else ApiKeyValidationState.UNAVAILABLE,
            stage,
            probe_model=probe_model,
        )

    error = payload.get("error") if isinstance(payload, dict) else None
    raw_error_type = error.get("type") if isinstance(error, dict) else None
    error_type = raw_error_type if isinstance(raw_error_type, str) else None
    # WHY: classify only provider evidence with an unambiguous actionable meaning;
    # 400 invalid_request_error can also describe request or account policy failures.
    mapping: dict[tuple[int, str], ApiKeyValidationState] = {
        (401, "authentication_error"): ApiKeyValidationState.INVALID,
        (402, "billing_error"): ApiKeyValidationState.NO_QUOTA,
        (403, "permission_error"): ApiKeyValidationState.PERMISSION_DENIED,
        (429, "rate_limit_error"): ApiKeyValidationState.RATE_LIMITED,
    }
    state = mapping.get((response.status_code, error_type)) if error_type is not None else None
    if state is None:
        state = ApiKeyValidationState.UNAVAILABLE
    return _result(state, stage, response=response, probe_model=probe_model)


def _effective_model(
    settings: AnthropicPluginSettings,
    registered_models: list[ModelEntry],
) -> tuple[str, str] | None:
    by_name = {entry.model_name: entry for entry in registered_models}
    selected = settings.validation_model
    if selected is None:
        selected = _PREFERRED_MODEL if _PREFERRED_MODEL in by_name else next(iter(by_name), None)
    entry = by_name.get(selected) if selected is not None else None
    if entry is None:
        return None
    upstream = entry.litellm_params.get("model")
    if not isinstance(upstream, str) or not upstream.startswith("anthropic/"):
        return None
    stripped = upstream.removeprefix("anthropic/")
    if not stripped or stripped.startswith("anthropic/"):
        return None
    return entry.model_name, stripped


class AnthropicApiKeyValidator:
    def __init__(
        self,
        *,
        settings: AnthropicPluginSettings,
        registered_models: list[ModelEntry],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._registered_models = registered_models
        self._transport = transport

    async def validate(self, api_key: str) -> ApiKeyValidationResult:
        model = _effective_model(self._settings, self._registered_models)
        if model is None:
            return _result(ApiKeyValidationState.MISCONFIGURED, None)
        probe_model, upstream_model = model
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self._settings.api_version,
        }

        async with ValidationHttpSession(transport=self._transport) as session:
            try:
                auth_response = await session.request_json(
                    "GET",
                    f"{_API_BASE}/models",
                    headers=headers,
                    params={"limit": 1},
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
                    f"{_API_BASE}/messages",
                    headers=headers,
                    json_body={
                        "model": upstream_model,
                        "max_tokens": 1,
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
