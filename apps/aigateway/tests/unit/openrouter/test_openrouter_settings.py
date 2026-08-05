"""OpenRouter plugin settings (OME-428 Phase 2, plan D2/D8).

Pins: disabled-by-default, env overrides via AIGW_OPENROUTER_*, the three URL4
seed gateway IDs, and the D8 upstream model-ID syntax validator.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aigateway.plugins.openrouter_provider.settings import (
    OpenRouterPluginSettings,
    is_valid_upstream_model_id,
)

# Independent protocol pin: this is the single source in the test suite that fails when the
# canonical benchmark seed set changes. Dispatch tests consume the configured defaults so every
# newly pinned seed is exercised without copying this list again.
_SEEDS = [
    "openrouter/anthropic/claude-fable-5",
    "openrouter/anthropic/claude-haiku-4.5",
    "openrouter/openai/gpt-5.5",
    "openrouter/anthropic/claude-opus-4.8",
    "openrouter/google/gemini-3.1-pro-preview",
    # The remaining DRACO / IFEval small-model candidate lineup.
    "openrouter/google/gemini-3-flash-preview",
    "openrouter/moonshotai/kimi-k2.6",
    "openrouter/moonshotai/kimi-k3",
    "openrouter/deepseek/deepseek-v4-pro",
    "openrouter/qwen/qwen3.6-plus",
]


def test_enabled_defaults_false() -> None:
    assert OpenRouterPluginSettings().enabled is False


def test_default_models_are_exactly_the_declared_seeds() -> None:
    assert OpenRouterPluginSettings().default_models == _SEEDS


def test_enabled_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIGW_OPENROUTER_ENABLED", "true")
    assert OpenRouterPluginSettings().enabled is True


def test_default_models_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AIGW_OPENROUTER_DEFAULT_MODELS",
        '["openrouter/mistralai/mistral-large-3"]',
    )
    assert OpenRouterPluginSettings().default_models == ["openrouter/mistralai/mistral-large-3"]


def test_env_override_with_malformed_model_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIGW_OPENROUTER_DEFAULT_MODELS", '["openrouter/justoneword"]')
    with pytest.raises(ValidationError):
        OpenRouterPluginSettings()


def test_models_without_gateway_prefix_rejected() -> None:
    with pytest.raises(ValidationError):
        OpenRouterPluginSettings(default_models=["anthropic/claude-fable-5"])


@pytest.mark.parametrize(
    "upstream",
    [
        "anthropic/claude-fable-5",
        "openai/gpt-5.5",  # dots in the model base
        "anthropic/claude-opus-4.8",
        "openrouter/free",  # special router is syntactically ordinary (BYOK allows it)
        "openrouter/free:thinking",
        "mistralai/devstral-2.1:free",  # dotted base + variant
        "~legacy-author/some_model",  # ~ alias marker, underscore
        "a/b",  # minimal two segments
        "a1/b2:nitro",
    ],
)
def test_valid_upstream_model_ids(upstream: str) -> None:
    assert is_valid_upstream_model_id(upstream) is True


@pytest.mark.parametrize(
    "upstream",
    [
        "",  # empty
        "anthropic",  # one segment
        "a/b/c",  # extra slash
        "a//b",  # empty middle segment
        "/b",  # empty author
        "a/",  # empty model
        "a/b:",  # empty variant
        "a/b:c:d",  # extra colon
        ":free",  # no base
        "~/model",  # ~ without author characters
        "a b/c",  # whitespace
        "a\tb/c",  # control/tab
        "ä/b",  # Unicode author
        "a/претрен",  # Unicode model
        "a\\b/c",  # backslash
        "a%20b/c",  # percent escape
        "https://evil.example/x",  # scheme
        "a/b?x=1",  # query marker
        "a/b#frag",  # fragment marker
        ".hidden/model",  # author must start alphanumeric
        "a/-model",  # model must start alphanumeric
        "a/b:-variant",  # variant must start alphanumeric
        42,  # non-string
        None,
    ],
)
def test_invalid_upstream_model_ids(upstream: object) -> None:
    assert is_valid_upstream_model_id(upstream) is False
