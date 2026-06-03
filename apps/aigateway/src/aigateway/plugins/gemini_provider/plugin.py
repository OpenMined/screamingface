from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from litellm.llms.custom_llm import CustomLLMError
from litellm.types.utils import ModelResponse

from aigateway.core.oauth.identity import AccountIdentity
from aigateway.core.plugin_base import (
    ModelEntry,
    OAuthCodeExchangeRequest,
    OAuthConfig,
    OAuthStrategy,
    ProviderPluginBase,
)

from .auth import (
    GeminiOAuth,
    account_label_from_credentials,
    exchange_authorization_code,
    extract_account_identity,
)
from .chat_handler import ensure_litellm_gemini_provider_registered, get_litellm_gemini_handler
from .models import MODELS
from .oauth_config import (
    GEMINI_AUTHORIZE_EXTRA_PARAMS,
    GEMINI_AUTHORIZE_URL,
    GEMINI_CLIENT_ID,
    GEMINI_REDIRECT_PATH,
    GEMINI_SCOPES,
    GEMINI_TOKEN_URL,
)

if TYPE_CHECKING:
    from aigateway.core.credential_blob.store import CredentialBlobStore


_CLIENT_AUTH_HEADER_NAMES = {
    "authorization",
    "x-aigw-gemini-profile",
    "x-goog-api-key",
    "x-goog-user-project",
}


def _retry_after_header(exc: CustomLLMError) -> dict[str, str]:
    """Surface the provider's reset window as a Retry-After header.

    ``_error_from_response`` stashes the parsed delay on ``exc.retry_after``;
    promoting it to a header lets the gateway's retry loop honor the *real*
    window instead of guessing via exponential backoff.
    """
    seconds = getattr(exc, "retry_after", None)
    if seconds is None:
        return {}
    return {"Retry-After": str(math.ceil(seconds))}


def _detail_for_error(exc: CustomLLMError) -> dict[str, str]:
    status_code = int(exc.status_code or 502)
    code = "provider_error"
    if status_code in (401, 403):
        code = "auth_required"
    elif status_code == 429:
        code = "rate_limited"
    elif status_code >= 500:
        code = "provider_unavailable"
    return {"code": code, "message": exc.message}


class GeminiProviderPlugin(ProviderPluginBase):
    custom_llm_provider = "gemini-cli"

    def credential_service_provider(self) -> str:
        return "gemini"

    def register_models(self) -> list[ModelEntry]:
        return list(MODELS)

    def oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            authorize_url=GEMINI_AUTHORIZE_URL,
            token_url=GEMINI_TOKEN_URL,
            client_id=GEMINI_CLIENT_ID,
            scopes=GEMINI_SCOPES,
            redirect_path=GEMINI_REDIRECT_PATH,
            extra_authorize_params=GEMINI_AUTHORIZE_EXTRA_PARAMS,
        )

    def oauth_strategy_for(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
        http_client_factory: Any | None = None,
    ) -> OAuthStrategy:
        return GeminiOAuth(
            profile_name=profile_name,
            credential_store=credential_store,
            http_client_factory=http_client_factory,
        )

    async def exchange_oauth_code(self, request: OAuthCodeExchangeRequest) -> dict[str, Any]:
        return await exchange_authorization_code(
            request.code,
            request.code_verifier,
            redirect_uri=request.redirect_uri,
            http_client_factory=request.http_client_factory,
        )

    def account_label_from_credentials(self, credentials: dict[str, Any]) -> str | None:
        return account_label_from_credentials(credentials)

    async def extract_identity(
        self,
        credentials: dict[str, Any],
        *,
        http_client_factory: Any | None = None,
    ) -> AccountIdentity | None:
        identity = await extract_account_identity(
            credentials,
            http_client_factory=http_client_factory,
        )
        if identity is None:
            return None
        return AccountIdentity(
            sub=identity.subject,
            email=identity.email,
            name=identity.name,
            raw=identity.as_dict(),
        )

    def allows_chatless_profile(self) -> bool:
        return True

    def supports_chat_streaming(self) -> bool:
        return False

    def should_mark_profile_error_on_dispatch_status(self, status_code: int) -> bool:
        return status_code in (401, 403)

    def invalidate_profile_session(self, profile_name: str) -> None:
        get_litellm_gemini_handler().invalidate_session(profile_name)

    def prepare_chat_body(self, body: dict[str, Any]) -> dict[str, Any]:
        out = dict(body)
        # API-key fallback is gateway-owned via environment, not caller-supplied per request.
        out.pop("api_key", None)
        extra_headers = out.get("extra_headers")
        if isinstance(extra_headers, dict):
            out["extra_headers"] = {
                key: value
                for key, value in extra_headers.items()
                if isinstance(key, str) and key.lower() not in _CLIENT_AUTH_HEADER_NAMES
            }
        return out

    async def chat_completion(self, body: dict[str, Any]) -> Any:
        optional_params = {
            key: value
            for key, value in body.items()
            if key not in {"model", "messages", "api_key", "extra_headers", "timeout"}
        }
        try:
            return await get_litellm_gemini_handler().acompletion(
                model=body["model"],
                messages=body["messages"],
                api_base=None,
                custom_prompt_dict={},
                model_response=ModelResponse(),
                print_verbose=lambda *_args, **_kwargs: None,
                encoding=None,
                api_key=body.get("api_key"),
                logging_obj=None,
                optional_params=optional_params,
                headers=body.get("extra_headers"),
                timeout=body.get("timeout"),
            )
        except CustomLLMError as exc:
            raise HTTPException(
                status_code=int(exc.status_code or 502),
                detail=_detail_for_error(exc),
                headers=_retry_after_header(exc),
            ) from exc


ensure_litellm_gemini_provider_registered()

PLUGIN = GeminiProviderPlugin()
