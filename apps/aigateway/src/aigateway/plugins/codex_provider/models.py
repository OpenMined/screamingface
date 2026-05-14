from __future__ import annotations

from aigateway.core.plugin_base import ModelEntry

CODEX_MODEL_SLUGS = {
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
    "gpt-5.2",
}

MODELS: list[ModelEntry] = [
    ModelEntry(model_name=f"codex/{slug}", litellm_params={"model": f"codex/{slug}"})
    for slug in sorted(CODEX_MODEL_SLUGS, reverse=True)
]
