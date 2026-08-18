"""Direct OpenAI provider's seed, capability, and parameter contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aigateway.core.cache_ports import CacheBypass
from aigateway.core.standard_parameters import MAX_TOKENS_SCHEMA
from aigateway.plugins.openai_provider.plugin import PLUGIN, OpenAIProviderPlugin
from aigateway.plugins.openai_provider.settings import OpenAIPluginSettings

DEFAULT_MODELS = [
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
    "openai/gpt-5.5",
    "openai/gpt-5.1",
    "openai/gpt-5",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/o3",
    "openai/o4-mini",
]


def test_plugin_identity_and_api_key_only_transport() -> None:
    assert isinstance(PLUGIN, OpenAIProviderPlugin)
    assert PLUGIN.custom_llm_provider == "openai"
    assert PLUGIN.provider_display_name == "OpenAI"
    assert PLUGIN.supports_api_key() is True
    assert PLUGIN.oauth_config() is None
    assert PLUGIN.oauth_strategy_for("acct:connection") is None
    assert PLUGIN.available_auth_modes() == ("api_key",)
    assert PLUGIN.supports_chat_streaming() is False


def test_default_seed_and_readiness_model_are_explicit() -> None:
    assert PLUGIN.settings.default_models == DEFAULT_MODELS
    assert PLUGIN.settings.validation_model == "openai/gpt-5-nano"
    assert [entry.model_name for entry in PLUGIN.register_models()] == DEFAULT_MODELS
    assert [entry.litellm_params for entry in PLUGIN.register_models()] == [
        {"model": model} for model in DEFAULT_MODELS
    ]


def test_settings_accept_only_direct_openai_model_ids() -> None:
    with pytest.raises(ValidationError):
        OpenAIPluginSettings(default_models=["codex/gpt-5"])
    with pytest.raises(ValidationError):
        OpenAIPluginSettings(default_models=["openai/"])
    with pytest.raises(ValidationError):
        OpenAIPluginSettings(
            default_models=["openai/gpt-5"], validation_model="openrouter/openai/gpt-5"
        )


@pytest.mark.parametrize(
    "model",
    [
        "openai/gpt/5",
        "openai/https://example.invalid",
        "openai/gpt-5?variant=x",
        "openai/gpt-5#fragment",
        "openai/gpt%2d5",
        "openai/gpt\\5",
        "openai/gpt 5",
        "openai/gpt\n5",
        "openai/gpt-五",
        f"openai/{'x' * 129}",
    ],
)
def test_settings_reject_unsafe_or_unbounded_model_tokens(model: str) -> None:
    with pytest.raises(ValidationError):
        OpenAIPluginSettings(default_models=[model], validation_model=model)


def test_settings_require_nonempty_unique_seed_and_registered_validation_model() -> None:
    with pytest.raises(ValidationError):
        OpenAIPluginSettings(default_models=[])
    with pytest.raises(ValidationError):
        OpenAIPluginSettings(
            default_models=["openai/gpt-5", "openai/gpt-5"],
            validation_model="openai/gpt-5",
        )
    with pytest.raises(ValidationError):
        OpenAIPluginSettings(
            default_models=["openai/gpt-5"],
            validation_model="openai/gpt-5-nano",
        )


def test_max_tokens_is_the_only_enabled_parameter() -> None:
    rules = PLUGIN.chat_parameter_rules(model="openai/gpt-5.6-sol", auth_type="api_key")

    assert len(rules) == 1
    rule = rules[0]
    assert rule.request_path == "max_tokens"
    assert rule.provider_target is None
    assert rule.parameter_schema == MAX_TOKENS_SCHEMA
    assert rule.applicable_auth_modes == ("api_key",)
    assert rule.cache_behavior == "bypass"


def test_max_tokens_has_locked_runtime_evidence() -> None:
    observations = PLUGIN.chat_parameter_observations(
        model="openai/gpt-5.6-sol", auth_type="api_key"
    )

    assert [(item.request_path, item.support, item.source) for item in observations] == [
        ("max_tokens", "supported", "openai:locked-runtime")
    ]


def test_provider_bypasses_global_cache_and_contributes_no_accounting_strategy() -> None:
    assert isinstance(
        PLUGIN.global_cache_projection(
            {"model": "openai/gpt-5.6-sol", "messages": [{"role": "user", "content": "hi"}]}
        ),
        CacheBypass,
    )
    assert not hasattr(PLUGIN, "usage_accounting_strategy")


@pytest.mark.parametrize(
    ("status_code", "marks_error"),
    [(200, False), (401, True), (403, False), (429, False), (500, False)],
)
def test_only_401_marks_the_selected_credential_invalid(
    status_code: int, marks_error: bool
) -> None:
    assert PLUGIN.should_mark_profile_error_on_dispatch_status(status_code) is marks_error
