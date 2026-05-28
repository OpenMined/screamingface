from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from litellm.llms.custom_llm import CustomLLMError
from litellm.types.utils import ModelResponse

from aigateway.core.oauth.identity import AccountIdentity, identity_from_id_token
from aigateway.core.plugin_base import (
    ModelEntry,
    OAuthCodeExchangeRequest,
    OAuthConfig,
    OAuthStrategy,
    ProviderPluginBase,
)

from .auth import CodexOAuth, account_label_from_credentials, exchange_authorization_code
from .chat_handler import (
    ensure_litellm_codex_provider_registered,
    get_litellm_codex_handler,
)
from .models import MODELS
from .oauth_config import (
    CODEX_AUTHORIZE_EXTRA_PARAMS,
    CODEX_AUTHORIZE_URL,
    CODEX_CLIENT_ID,
    CODEX_REDIRECT_PATH,
    CODEX_REDIRECT_PORTS,
    CODEX_SCOPES,
    CODEX_TOKEN_URL,
)

if TYPE_CHECKING:
    from aigateway.core.credential_blob.store import CredentialBlobStore


class CodexProviderPlugin(ProviderPluginBase):
    custom_llm_provider = "codex"

    def register_models(self) -> list[ModelEntry]:
        return list(MODELS)

    def oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            authorize_url=CODEX_AUTHORIZE_URL,
            token_url=CODEX_TOKEN_URL,
            client_id=CODEX_CLIENT_ID,
            scopes=CODEX_SCOPES,
            redirect_path=CODEX_REDIRECT_PATH,
            extra_authorize_params=CODEX_AUTHORIZE_EXTRA_PARAMS,
            loopback_redirect_ports=CODEX_REDIRECT_PORTS,
        )

    def oauth_strategy_for(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
        http_client_factory: Any | None = None,
    ) -> OAuthStrategy:
        return CodexOAuth(
            profile_name=profile_name,
            credential_store=credential_store,
            http_client_factory=http_client_factory,
        )

    async def exchange_oauth_code(self, request: OAuthCodeExchangeRequest) -> dict:
        return await exchange_authorization_code(
            request.code,
            request.code_verifier,
            redirect_uri=request.redirect_uri,
            http_client_factory=request.http_client_factory,
        )

    def account_label_from_credentials(self, credentials: dict) -> str | None:
        return account_label_from_credentials(credentials)

    async def extract_identity(
        self,
        credentials: dict[str, Any],
        *,
        http_client_factory: Any | None = None,  # noqa: ARG002
    ) -> AccountIdentity | None:
        return identity_from_id_token(credentials.get("id_token"))

    def supports_chat_streaming(self) -> bool:
        return False

    def prepare_chat_body(self, body: dict[str, Any]) -> dict[str, Any]:
        if "reasoning_effort" in body:
            effort = body.pop("reasoning_effort")
            if effort is not None and "reasoning" not in body:
                body["reasoning"] = {"effort": effort}
        return body

    async def chat_completion(self, body: dict[str, Any]) -> Any:
        optional_params = {
            key: value
            for key, value in body.items()
            if key not in {"model", "messages", "api_key", "extra_headers", "timeout"}
        }
        try:
            return await get_litellm_codex_handler().acompletion(
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
                status_code=exc.status_code,
                detail={"code": "provider_error", "message": exc.message},
            ) from exc


ensure_litellm_codex_provider_registered()

PLUGIN = CodexProviderPlugin()
