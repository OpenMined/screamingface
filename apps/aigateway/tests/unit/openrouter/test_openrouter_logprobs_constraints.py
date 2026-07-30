"""OpenRouter logprobs cross-field contract."""

from __future__ import annotations

import pytest

from aigateway.core.parameter_projection import IncompatibleParametersError
from aigateway.plugins.openrouter_provider.plugin import OpenRouterProviderPlugin

_MODEL = "openrouter/anthropic/claude-fable-5"


@pytest.mark.parametrize("logprobs", [None, False])
def test_top_logprobs_requires_logprobs_true(logprobs: bool | None) -> None:
    plugin = OpenRouterProviderPlugin()
    body = {"top_logprobs": 5}
    if logprobs is not None:
        body["logprobs"] = logprobs

    with pytest.raises(IncompatibleParametersError) as excinfo:
        plugin.validate_chat_parameter_combination(body, model=_MODEL, auth_mode="api_key")

    assert excinfo.value.paths == ("logprobs", "top_logprobs")


def test_top_logprobs_with_logprobs_true_is_accepted() -> None:
    OpenRouterProviderPlugin().validate_chat_parameter_combination(
        {"logprobs": True, "top_logprobs": 20},
        model=_MODEL,
        auth_mode="api_key",
    )
