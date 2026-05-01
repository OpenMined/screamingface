from __future__ import annotations

from aigateway.core.plugin_base import ModelEntry, OAuthStrategy, ProviderPluginBase

from .auth import AnthropicOAuth
from .models import MODELS


class AnthropicProviderPlugin(ProviderPluginBase):
    custom_llm_provider = "anthropic"

    def register_models(self) -> list[ModelEntry]:
        return list(MODELS)

    def oauth_strategy_for(self, profile_name: str) -> OAuthStrategy | None:
        # Task 5 will replace AnthropicOAuth's signature to take profile_name and
        # read per-profile keychain entries. For now, ignore profile_name and
        # construct the legacy single-instance strategy so existing live tests
        # and the SF-139 unit tests keep working.
        return AnthropicOAuth()


PLUGIN = AnthropicProviderPlugin()
