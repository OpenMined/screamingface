from __future__ import annotations

from aigateway.core.plugin_base import ModelEntry

_MODEL_SLUGS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

MODELS: list[ModelEntry] = [
    ModelEntry(model_name=f"gemini-cli/{slug}", litellm_params={"model": f"gemini-cli/{slug}"})
    for slug in _MODEL_SLUGS
]
