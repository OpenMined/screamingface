"""Canonical executable model catalog and engine registry."""

from __future__ import annotations

from dataclasses import dataclass

from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """One public URL4 model route and its private AI Gateway model id."""

    id: str
    gateway_model: str
    supported_tools: tuple[str, ...] = ()

    @property
    def route(self) -> str:
        return f"/{self.id}"


MODEL_ROUTES = (
    ModelRoute("codex/gpt-5.5", "codex/gpt-5.5"),
    ModelRoute("gemini/2.5", "gemini-cli/gemini-2.5-pro"),
    ModelRoute("claude/sonnet-4.6", "anthropic/claude-sonnet-4-6"),
)


def registry_document() -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": ["screamingface.fusion-result.v1"],
        "models": [
            {"id": model.id, "supported_tools": list(model.supported_tools)}
            for model in MODEL_ROUTES
        ],
        "reducers": [{"id": "majority_vote", "route": MAJORITY_VOTE_ROUTE}],
    }
