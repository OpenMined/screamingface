"""Plugin registry — discover, load, activate, and deactivate plugins."""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import pkgutil
from typing import Any

from screamingface.plugin import Plugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Manages the plugin lifecycle: discover → load → activate → deactivate."""

    def __init__(self) -> None:
        self._discovered: dict[str, importlib.metadata.EntryPoint | type[Plugin]] = {}
        self._active: dict[str, Plugin] = {}

    def discover(self) -> dict[str, importlib.metadata.EntryPoint | type[Plugin]]:
        """Scan entry_points and built-in plugin modules for Plugin subclasses."""
        # 1. External plugins via entry_points
        eps = importlib.metadata.entry_points()
        sf_eps = eps.select(group="screamingface.plugins")
        self._discovered = {ep.name: ep for ep in sf_eps}

        # 2. Built-in plugins from screamingface.plugins package
        try:
            import screamingface.plugins as plugins_pkg

            for _finder, name, _ispkg in pkgutil.iter_modules(plugins_pkg.__path__):
                try:
                    mod = importlib.import_module(f"screamingface.plugins.{name}.plugin")
                except ImportError:
                    logger.debug("No plugin module in screamingface.plugins.%s", name)
                    continue
                for attr in dir(mod):
                    cls = getattr(mod, attr)
                    if (
                        isinstance(cls, type)
                        and issubclass(cls, Plugin)
                        and cls is not Plugin
                        and cls.name
                    ):
                        self._discovered[cls.name] = cls
        except ImportError:
            logger.debug("No screamingface.plugins package found")

        logger.info("Discovered %d plugin(s): %s", len(self._discovered), list(self._discovered))
        return dict(self._discovered)

    def load_plugin(self, name: str) -> Plugin:
        """Load a plugin class by name and instantiate it."""
        entry = self._discovered.get(name)
        if entry is None:
            raise KeyError(f"Plugin {name!r} not found in discovered plugins")

        # Direct class reference (built-in plugin)
        if isinstance(entry, type) and issubclass(entry, Plugin):
            return entry()

        # EntryPoint (external plugin)
        plugin_cls = entry.load()
        if not isinstance(plugin_cls, type) or not issubclass(plugin_cls, Plugin):
            raise TypeError(f"Entry point {name!r} does not point to a Plugin subclass")
        return plugin_cls()

    def activate(self, plugin: Plugin, **kwargs: Any) -> None:
        """Activate a loaded plugin instance.

        Checks dependencies, system deps, and preflight before calling setup().
        If any check fails, the plugin is skipped with a warning instead of
        crashing the server.
        """
        if plugin.name in self._active:
            logger.warning("Plugin %r is already active", plugin.name)
            return

        # Check conflicts — warn & skip if a conflicting plugin is active
        for conflict in plugin.conflicts:
            if conflict in self._active:
                logger.warning(
                    "Plugin %r skipped: conflicts with active plugin %r",
                    plugin.name,
                    conflict,
                )
                return

        # Check dependencies — warn & skip instead of raising
        for dep in plugin.depends:
            if dep not in self._active:
                logger.warning(
                    "Plugin %r skipped: depends on %r, which is not active", plugin.name, dep
                )
                return

        # Resolve typed settings
        if plugin.settings_class is not None:
            app = kwargs.get("app")
            raw_config: dict[str, Any] = {}
            if app and hasattr(app.state, "config"):
                raw_config = app.state.config.plugin_config.get(plugin.name, {})
            plugin.settings = plugin.settings_class(**raw_config)

        # Run plugin preflight check (includes system_deps validation)
        ok, reason = plugin.preflight()
        if not ok:
            logger.warning("Plugin %r skipped: %s", plugin.name, reason)
            return

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
            raise RuntimeError(f"Cannot deactivate {name!r}: plugins {dependents} depend on it")

        plugin.teardown()
        del self._active[name]
        logger.info("Deactivated plugin: %s", name)

    def activate_all(self, names: list[str], **kwargs: Any) -> list[Plugin]:
        """Activate plugins in dependency order (topological sort).

        Plugins whose dependencies are not satisfied are skipped with a warning
        instead of crashing.
        """
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
                    logger.warning(
                        "Plugin %r skipped: depends on %r, which is not available",
                        name,
                        dep,
                    )
                    return
            self.activate(plugin, **kwargs)
            if plugin.name in self._active:
                activated.append(plugin)

        for name in names:
            _activate(name)

        return activated

    @property
    def active_plugins(self) -> dict[str, Plugin]:
        """Return a copy of active plugins."""
        return dict(self._active)

    @property
    def discovered_plugins(self) -> dict[str, importlib.metadata.EntryPoint | type[Plugin]]:
        """Return a copy of discovered plugins."""
        return dict(self._discovered)
