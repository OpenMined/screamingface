"""Loader auto-discovers provider packages when scanning aigateway.plugins.*."""

from __future__ import annotations

from aigateway.core.loader import load_plugins
from aigateway.core.registry import ProviderRegistry


def test_loader_discovers_anthropic_provider() -> None:
    reg = ProviderRegistry()
    load_plugins(reg)
    plugin = reg.get("anthropic")
    assert plugin is not None
    assert plugin.custom_llm_provider == "anthropic"
    models = plugin.register_models()
    names = {m.model_name for m in models}
    assert "claude-sonnet-4-5" in names
    for m in models:
        assert m.litellm_params["model"].startswith("anthropic/")


def test_loader_discovers_codex_provider() -> None:
    reg = ProviderRegistry()
    load_plugins(reg)
    plugin = reg.get("codex")
    assert plugin is not None
    assert plugin.custom_llm_provider == "codex"
    models = plugin.register_models()
    names = {m.model_name for m in models}
    assert "codex/gpt-5.4-mini" in names
    assert "codex/codex-auto-review" not in names
    for m in models:
        assert m.litellm_params["model"].startswith("codex/")


def test_loader_discovers_antigravity_provider() -> None:
    reg = ProviderRegistry()
    load_plugins(reg)
    plugin = reg.get("antigravity")
    assert plugin is not None
    assert plugin.custom_llm_provider == "antigravity"
    models = plugin.register_models()
    names = {m.model_name for m in models}
    assert "antigravity/gemini-3-flash" in names
    for m in models:
        assert m.litellm_params["model"].startswith("antigravity/")
