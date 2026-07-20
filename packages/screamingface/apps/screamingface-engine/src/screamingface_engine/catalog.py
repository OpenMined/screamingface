"""Canonical executable model catalog and engine registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE
from screamingface_engine.settings import MAX_REQUEST_TARGET_BYTES

type AuthMethod = Literal["oauth", "api_key"]


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    """One public provider identity and its private AI Gateway adapter details."""

    id: str
    display_name: str
    gateway_provider: str
    auth_methods: tuple[AuthMethod, ...]
    callback_path: str


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """One public URL4 model route and its private AI Gateway model id."""

    id: str
    gateway_model: str
    provider: str
    tool_capabilities: tuple[str, ...] = ()

    @property
    def route(self) -> str:
        return f"/{self.id}"


PROVIDER_ROUTES = (
    ProviderRoute("codex", "OpenAI Codex", "codex", ("oauth",), "/auth/callback"),
    ProviderRoute(
        "gemini",
        "Google Gemini",
        "gemini-cli",
        ("oauth", "api_key"),
        "/oauth2callback",
    ),
    ProviderRoute(
        "anthropic",
        "Anthropic",
        "anthropic",
        ("oauth", "api_key"),
        "/callback",
    ),
)


MODEL_ROUTES = (
    ModelRoute("codex/gpt-5.5", "codex/gpt-5.5", "codex"),
    ModelRoute("gemini/2.5", "gemini-cli/gemini-2.5-pro", "gemini", ("web_search",)),
    ModelRoute("claude/sonnet-4.6", "anthropic/claude-sonnet-4-6", "anthropic", ("web_search",)),
    ModelRoute("gemini/3.1-pro-preview", "gemini-cli/gemini-3.1-pro-preview", "gemini"),
)


def registry_document(
    *,
    enabled_tools: tuple[str, ...] = (),
    max_request_target_bytes: int = MAX_REQUEST_TARGET_BYTES,
) -> dict[str, object]:
    enabled = frozenset(enabled_tools)
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": ["screamingface.fusion-result.v1"],
        "limits": {"max_request_target_bytes": max_request_target_bytes},
        "providers": [
            {
                "id": provider.id,
                "display_name": provider.display_name,
                "auth_methods": list(provider.auth_methods),
            }
            for provider in PROVIDER_ROUTES
        ],
        "models": [
            {
                "id": model.id,
                "provider": model.provider,
                "supported_tools": [tool for tool in model.tool_capabilities if tool in enabled],
            }
            for model in MODEL_ROUTES
        ],
        "reducers": [{"id": "majority_vote", "route": MAJORITY_VOTE_ROUTE}],
    }
