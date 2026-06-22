from __future__ import annotations

from aigateway.core.plugin_base import ModelEntry

from .settings import _default_models

# Confirmed-served seed (findings U1). Single source of truth is the settings
# factory so the plugin and any direct importers agree; SF derives its dropdown
# from the gateway /v1/models registry (SF-284), not from a copied list.
MODELS: list[ModelEntry] = _default_models()
