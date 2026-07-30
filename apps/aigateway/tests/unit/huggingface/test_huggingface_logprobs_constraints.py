"""Hugging Face logprobs dependency and provider-local bound."""

from __future__ import annotations

import pytest

from aigateway.core.parameter_projection import (
    IncompatibleParametersError,
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from aigateway.plugins.huggingface_provider.plugin import HuggingFaceProviderPlugin

_MODEL = "huggingface/openai/gpt-oss-120b:cerebras"


@pytest.mark.parametrize("logprobs", [None, False])
def test_top_logprobs_requires_logprobs_true(logprobs: bool | None) -> None:
    plugin = HuggingFaceProviderPlugin()
    body = {"top_logprobs": 5}
    if logprobs is not None:
        body["logprobs"] = logprobs

    with pytest.raises(IncompatibleParametersError) as excinfo:
        plugin.validate_chat_parameter_combination(body, model=_MODEL, auth_mode="api_key")

    assert excinfo.value.paths == ("logprobs", "top_logprobs")


def test_top_logprobs_with_logprobs_true_is_accepted_at_five() -> None:
    HuggingFaceProviderPlugin().validate_chat_parameter_combination(
        {"logprobs": True, "top_logprobs": 5},
        model=_MODEL,
        auth_mode="api_key",
    )


def test_huggingface_rejects_top_logprobs_above_five() -> None:
    plugin = HuggingFaceProviderPlugin()
    rules = plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key")

    with pytest.raises(UnsupportedParametersError) as excinfo:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": [], "logprobs": True, "top_logprobs": 6},
            rules=rules,
            auth_mode="api_key",
        )

    assert excinfo.value.rejected == {"top_logprobs": "malformed"}
