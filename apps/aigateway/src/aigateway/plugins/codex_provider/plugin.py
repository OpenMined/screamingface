from __future__ import annotations

from typing import TYPE_CHECKING

import litellm

from aigateway.core.plugin_base import ModelEntry, OAuthStrategy, ProviderPluginBase

from .auth import CodexOAuth
from .bootstrap import bootstrap_from_codex_cli
from .litellm_handler import HANDLER
from .models import CODEX_MODEL_SLUGS, MODELS
from .routes import router

if TYPE_CHECKING:
    from aigateway.core.credential_store import CredentialStore
    from aigateway.core.profile_index import ProfileIndexStore


def ensure_litellm_codex_provider_registered() -> None:
    # LiteLLM 1.83 lists these subscription slugs as OpenAI chat models.
    # Its OpenAI branch runs before custom providers, so remove only these
    # slugs from that shortcut while preserving explicit `openai/...` routing.
    for slug in CODEX_MODEL_SLUGS:
        litellm.open_ai_chat_completion_models.discard(slug)

    existing = [entry for entry in litellm.custom_provider_map if entry.get("provider") == "codex"]
    if existing:
        return
    litellm.custom_provider_map.append({"provider": "codex", "custom_handler": HANDLER})


class CodexProviderPlugin(ProviderPluginBase):
    custom_llm_provider = "codex"

    def register_models(self) -> list[ModelEntry]:
        return list(MODELS)

    def oauth_strategy_for(self, profile_name: str) -> OAuthStrategy:
        return CodexOAuth(profile_name=profile_name)

    def auth_router(self):
        return router

    async def bootstrap_profiles(
        self,
        *,
        account_id: str,
        credential_store: CredentialStore | None = None,
        index_store: ProfileIndexStore | None = None,
    ) -> None:
        if index_store is None:
            return
        await bootstrap_from_codex_cli(account_id=account_id, index_store=index_store)


ensure_litellm_codex_provider_registered()
PLUGIN = CodexProviderPlugin()
