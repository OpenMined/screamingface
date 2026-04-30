from __future__ import annotations

from aigateway.core.plugin_base import ModelEntry, OAuthStrategy, ProviderPluginBase

from .auth import AnthropicOAuth
from .models import MODELS


class AnthropicProviderPlugin(ProviderPluginBase):
    custom_llm_provider = "anthropic"

    def __init__(self) -> None:
        self._strategy: AnthropicOAuth | None = None

    def register_models(self) -> list[ModelEntry]:
        return list(MODELS)

    def oauth_strategy(self) -> OAuthStrategy | None:
        if self._strategy is None:
            self._strategy = AnthropicOAuth()
        return self._strategy


PLUGIN = AnthropicProviderPlugin()
