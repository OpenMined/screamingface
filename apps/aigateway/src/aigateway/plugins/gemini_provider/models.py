from __future__ import annotations

from aigateway.core.plugin_base import ModelEntry

# gemini-3.1-flash-lite leads the list as the minimal stable readiness-probe default
# (see api_key_validation._PREFERRED_MODEL). gemini-2.0-flash was removed: Google shut it
# down on 2026-06-01, so advertising it would route chat and validation to a dead model.
_MODEL_SLUGS = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

MODELS: list[ModelEntry] = [
    ModelEntry(model_name=f"gemini-cli/{slug}", litellm_params={"model": f"gemini-cli/{slug}"})
    for slug in _MODEL_SLUGS
]
