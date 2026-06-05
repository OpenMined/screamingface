from __future__ import annotations

import os

from aigateway.core.plugin_base import ModelEntry
from aigateway.plugins.anthropic_provider.settings import AnthropicPluginSettings


def _clear_anthropic_env(monkeypatch) -> None:
    for key in list(os.environ):
        if key.startswith("AIGW_ANTHROPIC_"):
            monkeypatch.delenv(key, raising=False)


def test_anthropic_settings_defaults_preserve_current_values(monkeypatch) -> None:
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setenv("USER", "alice")

    settings = AnthropicPluginSettings()

    assert settings.authorize_url == "https://claude.com/cai/oauth/authorize"
    assert settings.token_url == "https://platform.claude.com/v1/oauth/token"
    assert settings.client_id == "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    assert settings.scopes == [
        "user:profile",
        "user:inference",
        "user:sessions:claude_code",
        "user:mcp_servers",
        "user:file_upload",
    ]
    assert settings.refresh_scopes == settings.scopes
    assert settings.redirect_path == "/callback"
    assert settings.authorize_extra_params == {"code": "true"}
    assert settings.api_version == "2023-06-01"
    assert "oauth-2025-04-20" in settings.beta
    assert settings.claude_code_keychain_service == "Claude Code-credentials"
    assert settings.keychain_account == "default"
    assert settings.bootstrap_user == "alice"
    assert [model.model_name for model in settings.models] == [
        "claude-sonnet-4-5",
        "claude-opus-4-7",
        "claude-haiku-4-5",
    ]
    assert settings.models[0].litellm_params == {"model": "anthropic/claude-sonnet-4-5"}


def test_anthropic_settings_env_overrides(monkeypatch) -> None:
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setenv("AIGW_ANTHROPIC_AUTHORIZE_URL", "https://auth.example/authorize")
    monkeypatch.setenv("AIGW_ANTHROPIC_TOKEN_URL", "https://auth.example/token")
    monkeypatch.setenv("AIGW_ANTHROPIC_CLIENT_ID", "client-env")
    monkeypatch.setenv("AIGW_ANTHROPIC_SCOPES", '["scope:one","scope:two"]')
    monkeypatch.setenv("AIGW_ANTHROPIC_REFRESH_SCOPES", '["scope:refresh"]')
    monkeypatch.setenv("AIGW_ANTHROPIC_REDIRECT_PATH", "/env-callback")
    monkeypatch.setenv("AIGW_ANTHROPIC_AUTHORIZE_EXTRA_PARAMS", '{"code":"false"}')
    monkeypatch.setenv("AIGW_ANTHROPIC_API_VERSION", "2024-01-01")
    monkeypatch.setenv("AIGW_ANTHROPIC_BETA", "beta-env")
    monkeypatch.setenv(
        "AIGW_ANTHROPIC_MODELS",
        '[{"model_name":"claude-env","litellm_params":{"model":"anthropic/claude-env"}}]',
    )
    monkeypatch.setenv("AIGW_ANTHROPIC_CLAUDE_CODE_KEYCHAIN_SERVICE", "CC Env")
    monkeypatch.setenv("AIGW_ANTHROPIC_KEYCHAIN_ACCOUNT", "account-env")
    monkeypatch.setenv("AIGW_ANTHROPIC_BOOTSTRAP_USER", "bootstrap-env")

    settings = AnthropicPluginSettings()

    assert settings.authorize_url == "https://auth.example/authorize"
    assert settings.token_url == "https://auth.example/token"
    assert settings.client_id == "client-env"
    assert settings.scopes == ["scope:one", "scope:two"]
    assert settings.refresh_scopes == ["scope:refresh"]
    assert settings.redirect_path == "/env-callback"
    assert settings.authorize_extra_params == {"code": "false"}
    assert settings.api_version == "2024-01-01"
    assert settings.beta == "beta-env"
    assert settings.models == [
        ModelEntry(model_name="claude-env", litellm_params={"model": "anthropic/claude-env"})
    ]
    assert settings.claude_code_keychain_service == "CC Env"
    assert settings.keychain_account == "account-env"
    assert settings.bootstrap_user == "bootstrap-env"


def test_anthropic_settings_constructor_overrides_env(monkeypatch) -> None:
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setenv("AIGW_ANTHROPIC_TOKEN_URL", "https://env.example/token")
    monkeypatch.setenv(
        "AIGW_ANTHROPIC_MODELS",
        '[{"model_name":"claude-env","litellm_params":{"model":"anthropic/claude-env"}}]',
    )
    explicit_model = ModelEntry(
        model_name="claude-explicit",
        litellm_params={"model": "anthropic/claude-explicit"},
    )

    settings = AnthropicPluginSettings(
        token_url="https://explicit.example/token",
        models=[explicit_model],
    )

    assert settings.token_url == "https://explicit.example/token"
    assert settings.models == [explicit_model]


def test_anthropic_provider_uses_injected_settings() -> None:
    from aigateway.plugins.anthropic_provider.auth import AnthropicOAuth
    from aigateway.plugins.anthropic_provider.plugin import AnthropicProviderPlugin

    model = ModelEntry(
        model_name="claude-custom",
        litellm_params={"model": "anthropic/claude-custom"},
    )
    settings = AnthropicPluginSettings(
        authorize_url="https://custom.example/authorize",
        token_url="https://custom.example/token",
        client_id="client-custom",
        scopes=["scope:custom"],
        redirect_path="/custom-callback",
        authorize_extra_params={"code": "custom"},
        keychain_account="account-custom",
        models=[model],
    )

    plugin = AnthropicProviderPlugin(settings=settings)

    assert plugin.register_models() == [model]
    cfg = plugin.oauth_config()
    assert cfg.authorize_url == "https://custom.example/authorize"
    assert cfg.token_url == "https://custom.example/token"
    assert cfg.client_id == "client-custom"
    assert cfg.scopes == ["scope:custom"]
    assert cfg.redirect_path == "/custom-callback"
    assert cfg.extra_authorize_params == {"code": "custom"}
    strategy = plugin.oauth_strategy_for("work")
    assert isinstance(strategy, AnthropicOAuth)
    assert strategy.credential_account() == "account-custom"
