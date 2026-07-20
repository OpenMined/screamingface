from __future__ import annotations

import pytest

from screamingface_engine.catalog import GatewayModel, resolve_model_routes


def test_gateway_catalog_forwards_every_supported_provider_model_in_order() -> None:
    routes = resolve_model_routes(
        (
            GatewayModel("claude-opus-4-8", "anthropic"),
            GatewayModel("claude-sonnet-4-6", "anthropic"),
            GatewayModel("codex/gpt-5.5", "codex"),
            GatewayModel("codex/gpt-5.4-mini", "codex"),
            GatewayModel("gemini-cli/gemini-2.5-pro", "gemini-cli"),
            GatewayModel("gemini-cli/gemini-2.0-flash", "gemini-cli"),
            GatewayModel("antigravity/gemini-3-flash", "antigravity"),
            GatewayModel("huggingface/Qwen/Qwen3:novita", "huggingface"),
        )
    )

    assert [(route.id, route.gateway_model, route.provider) for route in routes] == [
        ("claude/opus-4.8", "anthropic/claude-opus-4-8", "anthropic"),
        ("claude/sonnet-4.6", "anthropic/claude-sonnet-4-6", "anthropic"),
        ("codex/gpt-5.5", "codex/gpt-5.5", "codex"),
        ("codex/gpt-5.4-mini", "codex/gpt-5.4-mini", "codex"),
        ("gemini/2.5-pro", "gemini-cli/gemini-2.5-pro", "gemini"),
        ("gemini/2.0-flash", "gemini-cli/gemini-2.0-flash", "gemini"),
        (
            "huggingface/Qwen/Qwen3~novita",
            "huggingface/Qwen/Qwen3:novita",
            "huggingface",
        ),
    ]
    assert routes[0].tool_capabilities == ()
    assert routes[1].tool_capabilities == ()


@pytest.mark.parametrize(
    "models",
    [
        (),
        (GatewayModel("openrouter/model", "openrouter"),),
    ],
)
def test_catalog_requires_at_least_one_supported_provider_model(
    models: tuple[GatewayModel, ...],
) -> None:
    with pytest.raises(ValueError, match="no models for a supported provider"):
        resolve_model_routes(models)


def test_catalog_rejects_duplicate_public_routes() -> None:
    with pytest.raises(ValueError, match="duplicate public model ID 'codex/gpt-5.5'"):
        resolve_model_routes(
            (
                GatewayModel("codex/gpt-5.5", "codex"),
                GatewayModel("codex/gpt-5.5", "codex"),
            )
        )


@pytest.mark.parametrize(
    "model",
    [
        GatewayModel("claude-sonnet-latest", "anthropic"),
        GatewayModel("gpt-5.5", "codex"),
        GatewayModel("gemini-cli/not-gemini", "gemini-cli"),
        GatewayModel("huggingface/Qwen/Qwen3", "huggingface"),
    ],
)
def test_supported_provider_aliases_are_strict(model: GatewayModel) -> None:
    with pytest.raises(ValueError, match="cannot derive public model ID"):
        resolve_model_routes((model,))
