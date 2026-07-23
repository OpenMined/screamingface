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

from .response_errors import EmbeddedOpenRouterError, find_raw_error
from .settings import GATEWAY_MODEL_PREFIX, OpenRouterPluginSettings, is_valid_upstream_model_id

_API_BASE = "https://openrouter.ai/api/v1"
_INTERNAL_DEFAULT_MODEL = "openrouter/openrouter/free"
# WHY (OME-307 M-2): every OpenRouter typed error is only trustworthy when it rides on the HTTP
# status it implies, so each maps to (expected_status, actionable_state) and is honoured ONLY when
# the status evidence agrees (see _typed_error_evidence + _state_from_error). authentication /
# payment_required / permission_denied / rate_limit_exceeded are valid at any stage; not_found /
# invalid_request indict the readiness PROBE MODEL (gateway-controlled, not the key) and so map to
# MISCONFIGURED, but ONLY on the readiness stage.
_TYPED_ERROR_EVIDENCE: dict[str, tuple[int, ApiKeyValidationState]] = {
    "authentication": (401, ApiKeyValidationState.INVALID),
    "payment_required": (402, ApiKeyValidationState.NO_QUOTA),
    "permission_denied": (403, ApiKeyValidationState.PERMISSION_DENIED),
    "rate_limit_exceeded": (429, ApiKeyValidationState.RATE_LIMITED),
}
_READINESS_TYPED_ERROR_EVIDENCE: dict[str, tuple[int, ApiKeyValidationState]] = {
    "not_found": (404, ApiKeyValidationState.MISCONFIGURED),
    "invalid_request": (400, ApiKeyValidationState.MISCONFIGURED),
}


def _typed_error_evidence(
    error_type: str | None,
    stage: ApiKeyValidationStage,
) -> tuple[int, ApiKeyValidationState] | None:
    if error_type is None:
        return None
    evidence = _TYPED_ERROR_EVIDENCE.get(error_type)
    if evidence is not None:
        return evidence
    # INVARIANT (OME-307 M-2): not_found/invalid_request are actionable ONLY on the readiness probe;
    # at the authentication stage they stay non-actionable and fall through to UNAVAILABLE.
    if stage is ApiKeyValidationStage.READINESS:
        return _READINESS_TYPED_ERROR_EVIDENCE.get(error_type)
    return None


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


def _state_from_error(
    status: int,
    embedded: EmbeddedOpenRouterError,
    stage: ApiKeyValidationStage,
) -> ApiKeyValidationState:
    typed_evidence = _typed_error_evidence(embedded.error_type, stage)
    if typed_evidence is not None:
        expected_status, typed_state = typed_evidence
        # INVARIANT (OME-307 M-2): honour the typed state ONLY when the HTTP evidence agrees. The
        # outer status must be 200 (embedded-only error) or the expected status; the embedded
        # status, when present, must equal the expected status. Any contradiction is treated as an
        # upstream fault -> UNAVAILABLE (conservative), never an actionable state on bad evidence.
        contradictory = (
            (embedded.status is not None and embedded.status != expected_status)
            or (status != 200 and status != expected_status)
            or (stage is ApiKeyValidationStage.AUTHENTICATION and expected_status == 402)
        )
        if contradictory:
            return ApiKeyValidationState.UNAVAILABLE
        return typed_state
    if embedded.error_type is not None:
        return ApiKeyValidationState.UNAVAILABLE
    if status != 200 and embedded.status is not None and embedded.status != status:
        return ApiKeyValidationState.UNAVAILABLE
    resolved_status = embedded.status or status
    if resolved_status == 401:
        state = ApiKeyValidationState.INVALID
    elif resolved_status == 402:
        state = (
            ApiKeyValidationState.NO_QUOTA
            if stage is ApiKeyValidationStage.READINESS
            else ApiKeyValidationState.UNAVAILABLE
        )
    elif resolved_status == 403:
        state = ApiKeyValidationState.PERMISSION_DENIED
    elif resolved_status == 429:
        state = ApiKeyValidationState.RATE_LIMITED
    elif stage is ApiKeyValidationStage.READINESS and resolved_status in (400, 404):
        state = ApiKeyValidationState.MISCONFIGURED
    else:
        state = ApiKeyValidationState.UNAVAILABLE
    return state


def _classify(
    response: BoundedJsonResponse,
    stage: ApiKeyValidationStage,
    probe_model: str,
) -> ApiKeyValidationResult:
    payload = response.payload
    embedded = find_raw_error(payload) if isinstance(payload, dict) else EmbeddedOpenRouterError()
    if response.status_code == 200 and not embedded.found:
        if not isinstance(payload, dict):
            success = False
        elif stage is ApiKeyValidationStage.AUTHENTICATION:
            success = isinstance(payload.get("data"), dict)
        else:
            choices = payload.get("choices")
            success = isinstance(choices, list) and bool(choices)
        return _result(
            ApiKeyValidationState.VALID if success else ApiKeyValidationState.UNAVAILABLE,
            stage,
            probe_model=probe_model,
        )

    state = _state_from_error(response.status_code, embedded, stage)
    return _result(state, stage, response=response, probe_model=probe_model)


def _effective_model(settings: OpenRouterPluginSettings) -> tuple[str, str] | None:
    selected = settings.validation_model
    explicitly_set = "validation_model" in settings.model_fields_set
    # WHY: the hidden free router is the built-in readiness probe, not an advertised model seed.
    if (
        explicitly_set
        and selected != _INTERNAL_DEFAULT_MODEL
        and selected not in settings.default_models
    ):
        return None
    if not selected.startswith(GATEWAY_MODEL_PREFIX):
        return None
    upstream = selected[len(GATEWAY_MODEL_PREFIX) :]
    if not is_valid_upstream_model_id(upstream):
        return None
    return selected, upstream


class OpenRouterApiKeyValidator:
    def __init__(
        self,
        *,
        settings: OpenRouterPluginSettings,
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
                    f"{_API_BASE}/key",
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
