from __future__ import annotations

import os

from aigateway.plugins.gemini_provider.api_key_validation import GeminiApiKeyValidator
from aigateway.plugins.gemini_provider.models import MODELS
from aigateway.plugins.gemini_provider.plugin import GeminiProviderPlugin
from aigateway.plugins.gemini_provider.settings import GeminiPluginSettings


def _clear_gemini_env(monkeypatch) -> None:
    for key in list(os.environ):
        if key.startswith("AIGW_GEMINI_"):
            monkeypatch.delenv(key, raising=False)


def test_gemini_settings_default_validation_model_is_none(monkeypatch) -> None:
    _clear_gemini_env(monkeypatch)

    settings = GeminiPluginSettings()

    # WHY: None means "use the registered stable probe default" — the validator,
    # not settings, owns the fallback so an unset operator gets gemini-3.1-flash-lite.
    assert settings.validation_model is None


def test_gemini_settings_env_override_sets_validation_model(monkeypatch) -> None:
    _clear_gemini_env(monkeypatch)
    monkeypatch.setenv("AIGW_GEMINI_VALIDATION_MODEL", "gemini-cli/gemini-2.5-pro")

    settings = GeminiPluginSettings()

    assert settings.validation_model == "gemini-cli/gemini-2.5-pro"


def test_gemini_settings_constructor_overrides_env(monkeypatch) -> None:
    _clear_gemini_env(monkeypatch)
    monkeypatch.setenv("AIGW_GEMINI_VALIDATION_MODEL", "gemini-cli/gemini-2.5-pro")

    settings = GeminiPluginSettings(validation_model="gemini-cli/gemini-2.5-flash")

    assert settings.validation_model == "gemini-cli/gemini-2.5-flash"


def test_gemini_registers_stable_probe_and_drops_shutdown_model() -> None:
    names = [entry.model_name for entry in MODELS]

    # The current stable lite model is registered as the probe default...
    assert "gemini-cli/gemini-3.1-flash-lite" in names
    # ...and the model Google shut down on 2026-06-01 is no longer advertised.
    assert "gemini-cli/gemini-2.0-flash" not in names


def test_gemini_provider_passes_settings_and_models_to_validator() -> None:
    settings = GeminiPluginSettings(validation_model="gemini-cli/gemini-2.5-pro")
    plugin = GeminiProviderPlugin(settings=settings)

    validator = plugin.api_key_validator()

    assert isinstance(validator, GeminiApiKeyValidator)
    # One settings instance and the plugin's registered models flow into the validator.
    assert validator._settings is settings
    assert validator._registered_models == plugin.register_models()
