from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter


@dataclass(frozen=True)
class ModelEntry:
    """Single entry contributed to LiteLLM's model_list.

    Maps directly onto the dict shape that `litellm.Router(model_list=...)`
    expects. `model_name` is the user-facing alias; `litellm_params.model`
    is the fully-qualified provider/model string (e.g. `anthropic/claude-...`).
    """

    model_name: str
    litellm_params: dict[str, Any]


class OAuthStrategy(ABC):
    """Per-provider credential producer.

    Implementations own keychain reads, refresh-on-401 with locking, and
    any provider-specific header construction. The OAuth bridge calls
    `get_authorization_header()` right before LiteLLM dispatches a request.
    """

    @abstractmethod
    async def get_authorization_header(self) -> dict[str, str]:
        """Return headers to merge into the upstream request (e.g. `{"Authorization": "Bearer ..."}`)."""

    async def invalidate(self) -> None:
        """Drop any cached token. Called after a 401 from upstream."""


class ProviderPluginBase(ABC):
    """Contract for an aigateway provider plugin.

    Each plugin owns: model contributions, the OAuth strategy, and the
    auth UI router. The gateway core loads plugins, builds a litellm
    Router from their combined model lists, and mounts each auth router
    under `/v1/auth/{custom_llm_provider}`.
    """

    custom_llm_provider: str

    @abstractmethod
    def register_models(self) -> list[ModelEntry]:
        """Return the model_list entries this plugin contributes."""

    def oauth_strategy(self) -> OAuthStrategy | None:
        """Return the OAuth strategy for this provider, or None for no-auth providers (e.g. local Ollama)."""
        return None

    def auth_router(self) -> APIRouter | None:
        """Return a FastAPI router for `/v1/auth/{provider}` endpoints, or None."""
        return None
