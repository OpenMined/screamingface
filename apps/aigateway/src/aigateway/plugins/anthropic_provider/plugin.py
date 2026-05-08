from __future__ import annotations

from aigateway.core.plugin_base import (
    ModelEntry,
    OAuthConfig,
    OAuthStrategy,
    ProviderPluginBase,
)

from .auth import AnthropicOAuth
from .models import MODELS
from .oauth_config import (
    ANTHROPIC_AUTHORIZE_EXTRA_PARAMS,
    ANTHROPIC_AUTHORIZE_URL,
    ANTHROPIC_CLIENT_ID,
    ANTHROPIC_REDIRECT_PATH,
    ANTHROPIC_SCOPES,
    ANTHROPIC_TOKEN_URL,
)


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


PLUGIN = AnthropicProviderPlugin()
