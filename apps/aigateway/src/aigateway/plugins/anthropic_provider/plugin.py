from __future__ import annotations

from typing import TYPE_CHECKING

from aigateway.core.plugin_base import (
    ModelEntry,
    OAuthConfig,
    OAuthStrategy,
    ProviderPluginBase,
)

from .auth import AnthropicOAuth
from .bootstrap import bootstrap_from_claude_code
from .models import MODELS
from .oauth_config import (
    ANTHROPIC_AUTHORIZE_EXTRA_PARAMS,
    ANTHROPIC_AUTHORIZE_URL,
    ANTHROPIC_CLIENT_ID,
    ANTHROPIC_REDIRECT_PATH,
    ANTHROPIC_SCOPES,
    ANTHROPIC_TOKEN_URL,
)

if TYPE_CHECKING:
    from aigateway.core.credential_store import CredentialStore
    from aigateway.core.profile_index import ProfileIndexStore


class AnthropicProviderPlugin(ProviderPluginBase):
    custom_llm_provider = "anthropic"

    def register_models(self) -> list[ModelEntry]:
        return list(MODELS)

    def oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            authorize_url=ANTHROPIC_AUTHORIZE_URL,
            token_url=ANTHROPIC_TOKEN_URL,
            client_id=ANTHROPIC_CLIENT_ID,
            scopes=ANTHROPIC_SCOPES,
            redirect_path=ANTHROPIC_REDIRECT_PATH,
            extra_authorize_params=ANTHROPIC_AUTHORIZE_EXTRA_PARAMS,
        )

    def oauth_strategy_for(self, profile_name: str) -> OAuthStrategy:
        return AnthropicOAuth(profile_name=profile_name)

    async def bootstrap_profiles(
        self,
        *,
        account_id: str,
        credential_store: CredentialStore | None = None,
        index_store: ProfileIndexStore | None = None,
    ) -> None:
        await bootstrap_from_claude_code(
            account_id=account_id,
            credential_store=credential_store,
            index_store=index_store,
        )


PLUGIN = AnthropicProviderPlugin()
