"""Hugging Face provider settings: seed list + model-slug safety validator (SF-345).

The validator is the guard that keeps env overrides on the request-local routing
path. The unsafe provider-as-path-segment form
``huggingface/<provider>/<org>/<model>`` sends a malformed id to the unified router
(and, without the pinned ``api_base``, triggers an env-keyed huggingface.co mapping
lookup that ignores the per-request token), so it must be rejected up front.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aigateway.plugins.huggingface_provider.settings import (
    HuggingFacePluginSettings,
    _validate_model_slug,
)


def test_defaults_use_router_suffix_form() -> None:
    settings = HuggingFacePluginSettings()
    assert settings.default_models, "seed list must not be empty"
    for slug in settings.default_models:
        assert slug.startswith("huggingface/")
        # provider is encoded as a ":suffix", never as a path segment
        repo = slug[len("huggingface/") :].split(":", 1)[0]
        assert repo.count("/") == 1, f"seed {slug!r} is not '<org>/<model>'"


def test_router_api_base_default() -> None:
    assert HuggingFacePluginSettings().router_api_base == "https://router.huggingface.co/v1"


def test_bill_to_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIGW_HUGGINGFACE_BILL_TO", "OpenMinedFoundation")
    assert HuggingFacePluginSettings().bill_to == "OpenMinedFoundation"


def test_validator_accepts_suffix_and_bare_forms() -> None:
    assert (
        _validate_model_slug("huggingface/deepseek-ai/DeepSeek-R1:novita")
        == "huggingface/deepseek-ai/DeepSeek-R1:novita"
    )
    # bare '<org>/<model>' (router default provider) is also valid
    assert _validate_model_slug("huggingface/openai/gpt-oss-120b")


@pytest.mark.parametrize(
    "bad",
    [
        "huggingface/novita/deepseek-ai/DeepSeek-R1",  # provider-as-path-segment (forbidden)
        "huggingface/org/model/extra",  # too many path segments
        "huggingface/justmodel",  # missing '<org>/<model>' split
        "openai/gpt-oss-120b",  # missing 'huggingface/' prefix
        "huggingface/deepseek-ai/:novita",  # empty model
        "huggingface/org/model:",  # empty provider/policy suffix
        "huggingface/org/model::novita",  # malformed double-colon suffix
    ],
)
def test_validator_rejects_unsafe_or_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        _validate_model_slug(bad)


def test_env_override_accepts_valid_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AIGW_HUGGINGFACE_DEFAULT_MODELS",
        '["huggingface/deepseek-ai/DeepSeek-R1:novita", "huggingface/openai/gpt-oss-120b"]',
    )
    settings = HuggingFacePluginSettings()
    assert settings.default_models == [
        "huggingface/deepseek-ai/DeepSeek-R1:novita",
        "huggingface/openai/gpt-oss-120b",
    ]


def test_env_override_rejects_unsafe_path_segment_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An operator must not be able to silently reintroduce the unsafe routing form.
    monkeypatch.setenv(
        "AIGW_HUGGINGFACE_DEFAULT_MODELS",
        '["huggingface/novita/deepseek-ai/DeepSeek-R1"]',
    )
    with pytest.raises(ValidationError):
        HuggingFacePluginSettings()
