"""Canonical executable model catalog and engine registry."""

from __future__ import annotations

from dataclasses import dataclass

from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE
from screamingface_engine.settings import MAX_REQUEST_TARGET_BYTES


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """One public URL4 model route and its private AI Gateway model id."""

    id: str
    gateway_model: str
    tool_capabilities: tuple[str, ...] = ()

    @property
    def route(self) -> str:
        return f"/{self.id}"


MODEL_ROUTES = (
    ModelRoute("codex/gpt-5.5", "codex/gpt-5.5"),
    ModelRoute("gemini/2.5", "gemini-cli/gemini-2.5-pro", ("web_search",)),
    ModelRoute("claude/sonnet-4.6", "anthropic/claude-sonnet-4-6", ("web_search",)),
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
        "models": [
            {
                "id": model.id,
                "supported_tools": [tool for tool in model.tool_capabilities if tool in enabled],
            }
            for model in MODEL_ROUTES
        ],
        "reducers": [{"id": "majority_vote", "route": MAJORITY_VOTE_ROUTE}],
    }
