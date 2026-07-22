from __future__ import annotations

import math
import re
from typing import Any

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

from .message_adapter import build_generate_content_body, strip_provider_prefix
from .settings import GeminiPluginSettings

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_PREFERRED_MODEL = "gemini-cli/gemini-3.1-flash-lite"
_ERROR_INFO_TYPE = "type.googleapis.com/google.rpc.ErrorInfo"
_RETRY_INFO_TYPE = "type.googleapis.com/google.rpc.RetryInfo"
_BLOCKED_REASONS = frozenset(
    {
        "SERVICE_DISABLED",
        "API_KEY_SERVICE_BLOCKED",
        "API_KEY_HTTP_REFERRER_BLOCKED",
        "API_KEY_IP_ADDRESS_BLOCKED",
        "API_KEY_ANDROID_APP_BLOCKED",
        "API_KEY_IOS_APP_BLOCKED",
    }
)
_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)s$")


def _result(
    state: ApiKeyValidationState,
    stage: ApiKeyValidationStage | None,
    *,
    retry_after_seconds: int | None = None,
    probe_model: str | None = None,
) -> ApiKeyValidationResult:
    return ApiKeyValidationResult(
        state=state,
        stage=stage,
        retry_after_seconds=retry_after_seconds,
        probe_model=probe_model,
    )


def _details(payload: Any) -> tuple[str | None, list[dict[str, Any]]]:
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None, []
    status = error.get("status")
    raw_details = error.get("details")
    details = (
        [item for item in raw_details if isinstance(item, dict)]
        if isinstance(raw_details, list)
        else []
    )
    return status if isinstance(status, str) else None, details


def _error_info(details: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    for detail in details:
        if detail.get("@type") != _ERROR_INFO_TYPE:
            continue
        reason = detail.get("reason")
        domain = detail.get("domain")
        return (
            reason if isinstance(reason, str) else None,
            domain if isinstance(domain, str) else None,
        )
    return None, None


def _structured_retry_after(details: list[dict[str, Any]]) -> int | None:
    for detail in details:
        if detail.get("@type") != _RETRY_INFO_TYPE:
            continue
        value = detail.get("retryDelay")
        match = _DURATION_RE.fullmatch(value) if isinstance(value, str) else None
        if match is None:
            return None
        seconds = float(match.group(1))
        if not math.isfinite(seconds) or seconds <= 0:
            return None
        return math.ceil(seconds)
    return None


def _classify(
    response: BoundedJsonResponse,
    stage: ApiKeyValidationStage,
    probe_model: str,
) -> ApiKeyValidationResult:
    payload = response.payload
    if response.status_code == 200:
        if not isinstance(payload, dict):
            return _result(ApiKeyValidationState.UNAVAILABLE, stage, probe_model=probe_model)
        field = "models" if stage is ApiKeyValidationStage.AUTHENTICATION else "candidates"
        value = payload.get(field)
        success = isinstance(value, list) and (
            stage is ApiKeyValidationStage.AUTHENTICATION or bool(value)
        )
        return _result(
            ApiKeyValidationState.VALID if success else ApiKeyValidationState.UNAVAILABLE,
            stage,
            probe_model=probe_model,
        )

    status, details = _details(payload)
    reason, domain = _error_info(details)
    if response.status_code == 401 and status == "UNAUTHENTICATED":
        state = ApiKeyValidationState.INVALID
    elif response.status_code == 403 and status == "PERMISSION_DENIED":
        state = ApiKeyValidationState.PERMISSION_DENIED
    elif (
        response.status_code == 400
        and status == "INVALID_ARGUMENT"
        and reason == "API_KEY_INVALID"
        and domain == "googleapis.com"
    ):
        state = ApiKeyValidationState.INVALID
    elif (
        reason in _BLOCKED_REASONS
        and domain == "googleapis.com"
        and (
            (response.status_code == 400 and status in ("INVALID_ARGUMENT", "FAILED_PRECONDITION"))
            or (response.status_code == 403 and status == "PERMISSION_DENIED")
        )
    ):
        state = ApiKeyValidationState.PERMISSION_DENIED
    elif response.status_code == 429 and status == "RESOURCE_EXHAUSTED":
        state = ApiKeyValidationState.RATE_LIMITED
    else:
        state = ApiKeyValidationState.UNAVAILABLE

    retry_after = None
    if state is ApiKeyValidationState.RATE_LIMITED:
        retry_after = _structured_retry_after(details) or response.retry_after_seconds
    return _result(
        state,
        stage,
        retry_after_seconds=retry_after,
        probe_model=probe_model,
    )


def _effective_model(
    settings: GeminiPluginSettings,
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
    if not isinstance(upstream, str) or not upstream.startswith("gemini-cli/"):
        return None
    stripped = strip_provider_prefix(upstream)
    if not stripped or "/" in stripped:
        return None
    return entry.model_name, stripped


class GeminiApiKeyValidator:
    def __init__(
        self,
        *,
        settings: GeminiPluginSettings,
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
        headers = {"x-goog-api-key": api_key}

        async with ValidationHttpSession(transport=self._transport) as session:
            try:
                auth_response = await session.request_json(
                    "GET",
                    f"{_API_BASE}/models",
                    headers=headers,
                    params={"pageSize": 1},
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

            body = build_generate_content_body(
                [{"role": "user", "content": "ping"}],
                {"max_tokens": 1},
            )
            try:
                readiness_response = await session.request_json(
                    "POST",
                    f"{_API_BASE}/models/{upstream_model}:generateContent",
                    headers=headers,
                    json_body=body,
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
