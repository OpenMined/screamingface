"""Plugin registry — discover, load, activate, and deactivate plugins."""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Any

from screamingface.plugin import Plugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Manages the plugin lifecycle: discover → load → activate → deactivate."""

    def __init__(self) -> None:
        self._discovered: dict[str, importlib.metadata.EntryPoint] = {}
        self._active: dict[str, Plugin] = {}

    def discover(self) -> dict[str, importlib.metadata.EntryPoint]:
        """Scan entry_points for screamingface.plugins group."""
        eps = importlib.metadata.entry_points()
        sf_eps = eps.select(group="screamingface.plugins")
        self._discovered = {ep.name: ep for ep in sf_eps}
        logger.info("Discovered %d plugin(s): %s", len(self._discovered), list(self._discovered))
        return dict(self._discovered)

    def load_plugin(self, name: str) -> Plugin:
        """Load a plugin class by name and instantiate it."""
        ep = self._discovered.get(name)
        if ep is None:
            raise KeyError(f"Plugin {name!r} not found in discovered plugins")
        plugin_cls = ep.load()
        if not isinstance(plugin_cls, type) or not issubclass(plugin_cls, Plugin):
            raise TypeError(f"Entry point {name!r} does not point to a Plugin subclass")
        return plugin_cls()

    def activate(self, plugin: Plugin, **kwargs: Any) -> None:
        """Activate a loaded plugin instance."""
        if plugin.name in self._active:
            logger.warning("Plugin %r is already active", plugin.name)
            return

        # Check dependencies
        for dep in plugin.depends:
            if dep not in self._active:
                raise RuntimeError(
                    f"Plugin {plugin.name!r} depends on {dep!r}, which is not active"
                )

        plugin.setup(**kwargs)
        self._active[plugin.name] = plugin
        logger.info("Activated plugin: %s v%s", plugin.name, plugin.version)

    def deactivate(self, name: str) -> None:
        """Deactivate a plugin by name."""
        plugin = self._active.get(name)
        if plugin is None:
            raise KeyError(f"Plugin {name!r} is not active")

        # Check if other active plugins depend on this one
        dependents = [p.name for p in self._active.values() if name in p.depends]
        if dependents:
            raise RuntimeError(
                f"Cannot deactivate {name!r}: plugins {dependents} depend on it"
            )

        plugin.teardown()
        del self._active[name]
        logger.info("Deactivated plugin: %s", name)

    def activate_all(self, names: list[str], **kwargs: Any) -> list[Plugin]:
        """Activate plugins in dependency order (topological sort)."""
        plugins = {name: self.load_plugin(name) for name in names}
        activated: list[Plugin] = []
        visited: set[str] = set()

        def _activate(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            plugin = plugins[name]
            for dep in plugin.depends:
                if dep in plugins:
                    _activate(dep)
                elif dep not in self._active:
                    raise RuntimeError(
                        f"Plugin {name!r} depends on {dep!r}, which is not available"
                    )
            self.activate(plugin, **kwargs)
            activated.append(plugin)

        for name in names:
            _activate(name)

        return activated

    @property
    def active_plugins(self) -> dict[str, Plugin]:
        """Return a copy of active plugins."""
        return dict(self._active)

    @property
    def discovered_plugins(self) -> dict[str, importlib.metadata.EntryPoint]:
        """Return a copy of discovered plugins."""
        return dict(self._discovered)
