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

from .settings import HuggingFacePluginSettings

_IDENTITY_URL = "https://huggingface.co/api/whoami-v2"
_READINESS_URL = "https://router.huggingface.co/v1/chat/completions"
# WHY: default readiness probe must be ungated so validation never requires a
# per-model license acceptance. gpt-oss-120b is Apache-2.0 (no gate) and the
# :cerebras route is the explicit, test-pinned provider choice. It is the first
# entry in default_models, so this is also the first-seed fallback.
_PREFERRED_MODEL = "huggingface/openai/gpt-oss-120b:cerebras"


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
        elif stage is ApiKeyValidationStage.AUTHENTICATION:
            name = payload.get("name")
            success = isinstance(name, str) and bool(name) and isinstance(payload.get("auth"), dict)
        else:
            choices = payload.get("choices")
            success = isinstance(choices, list) and bool(choices)
        return _result(
            ApiKeyValidationState.VALID if success else ApiKeyValidationState.UNAVAILABLE,
            stage,
            probe_model=probe_model,
        )

    if response.status_code == 401:
        state = (
            ApiKeyValidationState.INVALID
            if stage is ApiKeyValidationStage.AUTHENTICATION
            else ApiKeyValidationState.PERMISSION_DENIED
        )
    elif response.status_code == 402:
        state = ApiKeyValidationState.NO_QUOTA
    elif response.status_code == 403:
        state = ApiKeyValidationState.PERMISSION_DENIED
    elif response.status_code == 429:
        state = ApiKeyValidationState.RATE_LIMITED
    else:
        state = ApiKeyValidationState.UNAVAILABLE
    return _result(state, stage, response=response, probe_model=probe_model)


def _effective_model(settings: HuggingFacePluginSettings) -> tuple[str, str] | None:
    selected = settings.validation_model
    if selected is None:
        selected = (
            _PREFERRED_MODEL
            if _PREFERRED_MODEL in settings.default_models
            else next(iter(settings.default_models), None)
        )
    if selected is None or selected not in settings.default_models:
        return None
    upstream = selected.removeprefix("huggingface/")
    if not upstream or upstream == selected:
        return None
    return selected, upstream


class HuggingFaceApiKeyValidator:
    def __init__(
        self,
        *,
        settings: HuggingFacePluginSettings,
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
                    _IDENTITY_URL,
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
                    _READINESS_URL,
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
