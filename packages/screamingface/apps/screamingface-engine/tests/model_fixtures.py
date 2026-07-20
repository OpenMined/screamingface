from __future__ import annotations

from screamingface_engine.catalog import GatewayModel, resolve_model_routes

GATEWAY_MODELS = (
    GatewayModel("codex/gpt-5.5", "codex"),
    GatewayModel("gemini-cli/gemini-2.5-flash", "gemini-cli"),
    GatewayModel("claude-sonnet-4-6", "anthropic"),
)
MODEL_ROUTES = resolve_model_routes(GATEWAY_MODELS)
