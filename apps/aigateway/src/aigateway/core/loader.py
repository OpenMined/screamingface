"""Discover provider plugins under `aigateway.plugins.*`.

Discovery rule: a direct subpackage contributes a provider when it has a
``plugin.py`` module exposing a module-level ``PLUGIN`` instance of
``ProviderPluginBase``. Other plugin packages may contribute non-provider
features and are ignored by this provider registry.

Kept deliberately simple — no entry-points, no plugin manifests, no
external discovery. Adding a provider = drop a folder under
`src/aigateway/plugins/` containing a `plugin.py` that sets `PLUGIN = ...`.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil

from .plugin_base import ProviderPluginBase
from .registry import ProviderRegistry

logger = logging.getLogger(__name__)


def load_plugins(registry: ProviderRegistry, package: str = "aigateway.plugins") -> None:
    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        logger.warning("plugins package %s not found; no providers loaded", package)
        return

    for info in pkgutil.iter_modules(pkg.__path__, prefix=f"{package}."):
        if not info.ispkg:
            continue
        plugin_module = f"{info.name}.plugin"
        try:
            if importlib.util.find_spec(plugin_module) is None:
                continue
            mod = importlib.import_module(plugin_module)
        except ModuleNotFoundError:
            logger.warning("provider plugin %s has an unavailable dependency; skipping", info.name)
            continue
        plugin = getattr(mod, "PLUGIN", None)
        if not isinstance(plugin, ProviderPluginBase):
            logger.warning(
                "plugin module %s does not export a ProviderPluginBase via PLUGIN; skipping",
                plugin_module,
            )
            continue
        registry.register(plugin)
        logger.info("loaded provider plugin: %s", plugin.custom_llm_provider)
