from __future__ import annotations

from screamingface_engine.catalog import MODEL_ROUTES


def test_engine_advertises_only_gateway_registered_model_ids() -> None:
    assert [(route.id, route.gateway_model) for route in MODEL_ROUTES] == [
        ("codex/gpt-5.5", "codex/gpt-5.5"),
        ("gemini/2.5-flash", "gemini-cli/gemini-2.5-flash"),
        ("claude/sonnet-4.6", "anthropic/claude-sonnet-4-6"),
    ]
