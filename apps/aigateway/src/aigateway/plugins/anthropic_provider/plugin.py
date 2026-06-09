from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aigateway.core.api_key_strategy import ApiKeyStrategy
from aigateway.core.oauth.identity import AccountIdentity
from aigateway.core.plugin_base import (
    CredentialStrategy,
    ModelEntry,
    OAuthCodeExchangeRequest,
    OAuthConfig,
    ProviderPluginBase,
)

from .auth import AnthropicOAuth, credential_service_for, exchange_authorization_code
from .bootstrap import bootstrap_from_claude_code
from .chat_handler import chat_completion, prepare_claude_code_body
from .settings import AnthropicPluginSettings

if TYPE_CHECKING:
    from aigateway.core.credential_blob.store import CredentialBlobStore
    from aigateway.core.profile_index import ProfileIndexStore


def _api_key_headers(api_key: str) -> dict[str, str]:
    # chat.py pops Authorization into body["api_key"]; LiteLLM then sends raw
    # (non-"sk-ant-oat") keys upstream as x-api-key, and only OAuth tokens get
    # the Bearer + oauth beta-header treatment.
    return {"Authorization": f"Bearer {api_key}"}


class AnthropicProviderPlugin(ProviderPluginBase[AnthropicPluginSettings]):
    custom_llm_provider = "anthropic"
    settings_cls = AnthropicPluginSettings

    def register_models(self) -> list[ModelEntry]:
        return list(self.settings.models)

    def oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            authorize_url=self.settings.authorize_url,
            token_url=self.settings.token_url,
            client_id=self.settings.client_id,
            scopes=list(self.settings.scopes),
            redirect_path=self.settings.redirect_path,
            extra_authorize_params=dict(self.settings.authorize_extra_params),
        )

    def oauth_strategy_for(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
        http_client_factory: Any | None = None,
    ) -> CredentialStrategy:
        return AnthropicOAuth(
            profile_name=profile_name,
            credential_store=credential_store,
            http_client_factory=http_client_factory,
            settings=self.settings,
        )

    def api_key_strategy_for(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
    ) -> CredentialStrategy:
        return ApiKeyStrategy(
            profile_name,
            service=credential_service_for(profile_name),
            account=self.settings.keychain_account,
            header_builder=_api_key_headers,
            credential_store=credential_store,
        )

    def should_apply_profile_default(self, field: str) -> bool:
        # The legacy SF Claude backend ignored default_effort. Applying it as a
        # gateway profile default enables Anthropic thinking on every request and
        # burns the Claude Code rate-limit pool unexpectedly.
        return field != "reasoning_effort"

    def prepare_chat_body(self, body: dict[str, Any]) -> dict[str, Any]:
        out = dict(body)
        if out.get("reasoning_effort") == "none":
            out.pop("reasoning_effort", None)
        return prepare_claude_code_body(out)

    async def chat_completion(self, body: dict[str, Any]) -> Any:
        return await chat_completion(body)

    async def exchange_oauth_code(self, request: OAuthCodeExchangeRequest) -> dict:
        return await exchange_authorization_code(
            request.code,
            request.code_verifier,
            redirect_uri=request.redirect_uri,
            state=request.state,
            http_client_factory=request.http_client_factory,
            settings=self.settings,
        )

    async def extract_identity(
        self,
        _credentials: dict[str, Any],
        *,
        http_client_factory: Any | None = None,  # noqa: ARG002
    ) -> AccountIdentity | None:
        return None

    def requires_oauth_connection_label(self) -> bool:
        return True

    async def bootstrap_profiles(
        self,
        *,
        account_id: str,
        credential_store: CredentialBlobStore | None = None,
        index_store: ProfileIndexStore | None = None,
    ) -> None:
        await bootstrap_from_claude_code(
            account_id=account_id,
            credential_store=credential_store,
            index_store=index_store,
            settings=self.settings,
        )


PLUGIN = AnthropicProviderPlugin()
