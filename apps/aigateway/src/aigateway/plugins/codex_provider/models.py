from __future__ import annotations

from aigateway.core.plugin_base import ModelEntry

_MODEL_SLUGS = [
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
    "gpt-5.2",
]

MODELS: list[ModelEntry] = [
    ModelEntry(model_name=f"codex/{slug}", litellm_params={"model": f"codex/{slug}"})
    for slug in _MODEL_SLUGS
]
