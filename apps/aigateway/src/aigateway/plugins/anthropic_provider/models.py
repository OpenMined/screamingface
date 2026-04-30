"""Anthropic models surfaced through the gateway.

Each entry maps the user-facing model name (used in OpenAI requests as
the ``model`` field) to LiteLLM's fully-qualified provider/model string.
LiteLLM's `get_llm_provider` parses the prefix to dispatch upstream.
"""

from __future__ import annotations

from aigateway.core.plugin_base import ModelEntry

MODELS: list[ModelEntry] = [
    ModelEntry(
        model_name="claude-sonnet-4-5",
        litellm_params={"model": "anthropic/claude-sonnet-4-5"},
    ),
    ModelEntry(
        model_name="claude-opus-4-7",
        litellm_params={"model": "anthropic/claude-opus-4-7"},
    ),
    ModelEntry(
        model_name="claude-haiku-4-5",
        litellm_params={"model": "anthropic/claude-haiku-4-5"},
    ),
]
