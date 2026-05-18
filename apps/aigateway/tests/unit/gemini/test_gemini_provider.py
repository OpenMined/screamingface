from __future__ import annotations

from aigateway.core.loader import load_plugins
from aigateway.core.registry import ProviderRegistry
from aigateway.plugins.gemini_provider.auth import GeminiOAuth
from aigateway.plugins.gemini_provider.oauth_config import (
    GEMINI_AUTHORIZE_URL,
    GEMINI_CLIENT_ID,
    GEMINI_REDIRECT_PATH,
    GEMINI_TOKEN_URL,
)
from aigateway.plugins.gemini_provider.plugin import GeminiProviderPlugin


def test_gemini_provider_loads_with_oauth_config_and_models() -> None:
    registry = ProviderRegistry()
    load_plugins(registry)

    plugin = registry.get("gemini-cli")

    assert plugin is not None
    assert plugin.custom_llm_provider == "gemini-cli"
    assert plugin.allows_chatless_profile() is True
    assert plugin.supports_chat_streaming() is False
    assert plugin.should_mark_profile_error_on_dispatch_status(401) is True
    assert plugin.should_mark_profile_error_on_dispatch_status(403) is True
    assert plugin.should_mark_profile_error_on_dispatch_status(429) is False
    cfg = plugin.oauth_config()
    assert cfg is not None
    assert cfg.authorize_url == GEMINI_AUTHORIZE_URL
    assert cfg.token_url == GEMINI_TOKEN_URL
    assert cfg.client_id == GEMINI_CLIENT_ID
    assert cfg.redirect_path == GEMINI_REDIRECT_PATH
    assert cfg.extra_authorize_params == {"access_type": "offline", "prompt": "consent"}
    assert "https://www.googleapis.com/auth/cloud-platform" in cfg.scopes
    assert "https://www.googleapis.com/auth/userinfo.email" in cfg.scopes
    assert "https://www.googleapis.com/auth/userinfo.profile" in cfg.scopes
    names = {entry.model_name for entry in plugin.register_models()}
    assert "gemini-cli/gemini-2.5-flash" in names
    assert "gemini-cli/gemini-2.5-pro" in names


def test_gemini_provider_creates_gemini_oauth_strategy() -> None:
    registry = ProviderRegistry()
    load_plugins(registry)
    plugin = registry.get("gemini-cli")
    assert plugin is not None

    strategy = plugin.oauth_strategy_for("default")

    assert isinstance(strategy, GeminiOAuth)
    assert strategy.profile_name == "default"


def test_prepare_chat_body_strips_caller_supplied_auth_headers() -> None:
    prepared = GeminiProviderPlugin().prepare_chat_body(
        {
            "model": "gemini-cli/gemini-2.5-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "api_key": "client-supplied",
            "extra_headers": {
                "Authorization": "Bearer attacker",
                "X-AIGW-Gemini-Profile": "attacker-profile",
                "x-goog-api-key": "attacker-key",
                "x-goog-user-project": "attacker-project",
                "X-Trace-Id": "trace-1",
            },
        }
    )

    assert "api_key" not in prepared
    assert prepared["extra_headers"] == {"X-Trace-Id": "trace-1"}


def test_models_route_includes_gemini_models(authenticated_client) -> None:
    response = authenticated_client.get("/v1/models")

    assert response.status_code == 200
    models = {entry["id"]: entry for entry in response.json()["data"]}
    assert models["gemini-cli/gemini-2.5-flash"]["owned_by"] == "gemini-cli"
