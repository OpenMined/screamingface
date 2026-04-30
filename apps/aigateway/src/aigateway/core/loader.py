"""Discover provider plugins under `aigateway.plugins.*`.

Discovery rule: every direct subpackage of `aigateway.plugins` is treated
as a plugin. Each plugin module must expose a module-level `PLUGIN`
attribute that is an instance of `ProviderPluginBase`.

Kept deliberately simple — no entry-points, no plugin manifests, no
external discovery. Adding a provider = drop a folder under
`src/aigateway/plugins/` containing a `plugin.py` that sets `PLUGIN = ...`.
"""

from __future__ import annotations

import importlib
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
            mod = importlib.import_module(plugin_module)
        except ModuleNotFoundError:
            logger.warning("plugin package %s has no plugin.py; skipping", info.name)
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
