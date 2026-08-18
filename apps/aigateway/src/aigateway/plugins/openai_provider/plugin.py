from __future__ import annotations

import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import httpx
from fastapi import HTTPException
from openai import AsyncOpenAI, Omit

from aigateway.core.api_key_strategy import ApiKeyStrategy
from aigateway.core.api_key_validation import ApiKeyValidator
from aigateway.core.plugin_base import CredentialStrategy, ModelEntry, ProviderPluginBase
from aigateway.core.request_hardening import strip_dispatch_controls
from aigateway.core.standard_parameters import direct_parameter_observations

from .api_key_validation import OpenAIApiKeyValidator
from .parameters import openai_chat_parameter_rules
from .settings import OpenAIPluginSettings

if TYPE_CHECKING:
    from aigateway.core.chat_parameters import (
        ParameterProjectionRule,
        ProviderParameterObservation,
    )
    from aigateway.core.credential_blob.store import CredentialBlobStore
    from aigateway.core.profile_models import AuthMode


_OBSERVATION_SOURCE = "openai:locked-runtime"
_OFFICIAL_API_BASE = "https://api.openai.com/v1"
_LITELLM_GLOBAL_CALLBACK_FIELDS = (
    "callbacks",
    "input_callback",
    "success_callback",
    "failure_callback",
    "_async_input_callback",
    "_async_success_callback",
    "_async_failure_callback",
)
_LITELLM_GLOBAL_RULE_FIELDS = (
    "pre_call_rules",
    "post_call_rules",
    "drop_params",
    "additional_drop_params",
)


def _credential_service_for(profile_name: str) -> str:
    return f"aigateway:openai:{profile_name}"


def _openai_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        verify=True,
        trust_env=False,
        follow_redirects=False,
    )


def _invalid_model_error() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "invalid_model",
            "provider": "openai",
            "message": "model is not registered for direct OpenAI dispatch",
        },
    )


def _unsafe_environment_error() -> HTTPException:
    error = HTTPException(
        status_code=503,
        detail={
            "code": "unsafe_openai_environment",
            "provider": "openai",
            "message": "direct OpenAI dispatch is unavailable",
        },
    )
    cast("Any", error).aigw_non_retryable = True
    return error


def _has_unsafe_litellm_global_state(litellm: Any, model: object) -> bool:
    aliases = getattr(litellm, "model_alias_map", None)
    if isinstance(model, str) and isinstance(aliases, Mapping) and model in aliases:
        return True
    if getattr(litellm, "model_fallbacks", None):
        return True
    if getattr(litellm, "headers", None):
        return True
    if getattr(litellm, "proxy_auth", None) is not None:
        return True
    if any(bool(getattr(litellm, field, None)) for field in _LITELLM_GLOBAL_RULE_FIELDS):
        return True
    return any(
        callbacks and any(callback != "cache" for callback in callbacks)
        for callbacks in (
            getattr(litellm, field, None) for field in _LITELLM_GLOBAL_CALLBACK_FIELDS
        )
    )


class OpenAIProviderPlugin(ProviderPluginBase[OpenAIPluginSettings]):
    custom_llm_provider = "openai"
    provider_display_name = "OpenAI"
    settings_cls = OpenAIPluginSettings

    def register_models(self) -> list[ModelEntry]:
        return [
            ModelEntry(model_name=model, litellm_params={"model": model})
            for model in self.settings.default_models
        ]

    def supports_api_key(self) -> bool:
        return True

    def supports_chat_streaming(self) -> bool:
        return False

    def api_key_strategy_for(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
    ) -> CredentialStrategy:
        return ApiKeyStrategy(
            profile_name,
            service=_credential_service_for(profile_name),
            account="default",
            header_builder=lambda api_key: {"Authorization": f"Bearer {api_key}"},
            credential_store=credential_store,
        )

    def should_mark_profile_error_on_dispatch_status(self, status_code: int) -> bool:
        return status_code == 401

    def api_key_validator(self) -> ApiKeyValidator:
        return OpenAIApiKeyValidator(settings=self.settings)

    def chat_parameter_rules(
        self, *, model: str, auth_type: AuthMode | None = None
    ) -> tuple[ParameterProjectionRule, ...]:
        return openai_chat_parameter_rules(model=model, auth_type=auth_type)

    def chat_parameter_observations(
        self, *, model: str, auth_type: AuthMode | None = None
    ) -> tuple[ProviderParameterObservation, ...]:
        del model, auth_type
        return direct_parameter_observations(("max_tokens",), source=_OBSERVATION_SOURCE)

    def prepare_chat_body(self, body: dict[str, Any]) -> dict[str, Any]:
        out = strip_dispatch_controls(body)
        model = out.get("model")
        if model not in self.settings.default_models:
            raise _invalid_model_error()
        out["api_base"] = _OFFICIAL_API_BASE
        return out

    async def chat_completion(self, body: dict[str, Any]) -> Any:
        import litellm

        if os.environ.get("OPENAI_CUSTOM_HEADERS"):
            raise _unsafe_environment_error()
        if _has_unsafe_litellm_global_state(litellm, body.get("model")):
            raise _unsafe_environment_error()

        dispatch_body = dict(body)
        api_key = dispatch_body.pop("api_key", None)
        if not isinstance(api_key, str) or not api_key:
            raise _unsafe_environment_error()
        dispatch_body["api_base"] = _OFFICIAL_API_BASE
        dispatch_body["caching"] = False
        dispatch_body["cache"] = {"no-cache": True, "no-store": True}
        dispatch_body["num_retries"] = 0
        dispatch_body["max_retries"] = 0
        dispatch_body["_skip_responses_api_bridge"] = True

        default_headers: dict[str, Any] = {
            "OpenAI-Organization": Omit(),
            "OpenAI-Project": Omit(),
        }
        http_client = _openai_http_client()
        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=_OFFICIAL_API_BASE,
                max_retries=0,
                default_headers=default_headers,
                http_client=http_client,
            )
        except Exception:
            await http_client.aclose()
            raise
        dispatch_body["client"] = client
        try:
            response = cast("Any", await litellm.acompletion(**dispatch_body))
        finally:
            await client.close()

        payload = response.model_dump() if hasattr(response, "model_dump") else response
        return cast("Any", payload)


PLUGIN = OpenAIProviderPlugin()
