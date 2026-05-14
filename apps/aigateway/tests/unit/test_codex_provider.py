from __future__ import annotations

from typing import cast

import litellm
from fastapi import APIRouter

from aigateway.core.loader import load_plugins
from aigateway.core.registry import ProviderRegistry


def test_loader_discovers_codex_provider_and_registers_custom_litellm_provider() -> None:
    reg = ProviderRegistry()
    load_plugins(reg)

    plugin = reg.get("codex")
    assert plugin is not None
    assert plugin.custom_llm_provider == "codex"
    assert plugin.oauth_config() is None
    auth_router = cast(APIRouter, plugin.auth_router())
    assert any(getattr(route, "path", None) == "/profiles/import" for route in auth_router.routes)
    assert {m.model_name for m in plugin.register_models()} == {
        "codex/gpt-5.5",
        "codex/gpt-5.4",
        "codex/gpt-5.4-mini",
        "codex/gpt-5.3-codex",
        "codex/gpt-5.2",
    }
    assert "gpt-5.4-mini" not in litellm.open_ai_chat_completion_models
    assert [entry.get("provider") for entry in litellm.custom_provider_map].count("codex") == 1
