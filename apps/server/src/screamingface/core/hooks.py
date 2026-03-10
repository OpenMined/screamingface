"""Signal/hook system for inter-plugin communication."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Built-in hook names (plugins can define their own too)
BUILTIN_HOOKS = frozenset(
    {
        "app.startup",
        "app.shutdown",
        "request.before",
        "request.after",
        "plugin.activated",
        "plugin.deactivated",
    }
)


@dataclass(order=True)
class HookEntry:
    """A registered callback for a specific hook."""

    priority: int
    callback: Callable[..., Any] = field(compare=False)
    plugin_name: str = field(compare=False)


class HookRegistry:
    """Register callbacks for named hooks, fire them by name."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookEntry]] = {}

    def register(
        self,
        hook_name: str,
        callback: Callable[..., Any],
        *,
        priority: int = 100,
        plugin_name: str = "",
    ) -> None:
        """Register a callback for a named hook.

        Lower priority numbers run first.
        """
        entries = self._hooks.setdefault(hook_name, [])
        entries.append(HookEntry(priority=priority, callback=callback, plugin_name=plugin_name))
        entries.sort()

    def emit(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Fire all callbacks for a hook, return list of results."""
        results: list[Any] = []
        for entry in self._hooks.get(hook_name, []):
            try:
                results.append(entry.callback(**kwargs))
            except Exception:
                logger.exception(
                    "Hook %r callback from plugin %r failed", hook_name, entry.plugin_name
                )
        return results

    async def emit_async(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Fire all callbacks for a hook (supports async callbacks)."""
        import asyncio

        results: list[Any] = []
        for entry in self._hooks.get(hook_name, []):
            try:
                result = entry.callback(**kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                results.append(result)
            except Exception:
                logger.exception(
                    "Hook %r callback from plugin %r failed", hook_name, entry.plugin_name
                )
        return results

    def emit_chain(self, hook_name: str, value: Any, **kwargs: Any) -> Any:
        """Pipe a value through all callbacks for a hook (pipeline pattern).

        Each callback receives the value returned by the previous one.
        """
        for entry in self._hooks.get(hook_name, []):
            try:
                value = entry.callback(value, **kwargs)
            except Exception:
                logger.exception(
                    "Hook %r chain callback from plugin %r failed", hook_name, entry.plugin_name
                )
        return value

    def unregister_plugin(self, plugin_name: str) -> None:
        """Remove all hooks registered by a specific plugin."""
        for hook_name in list(self._hooks):
            self._hooks[hook_name] = [
                e for e in self._hooks[hook_name] if e.plugin_name != plugin_name
            ]
            if not self._hooks[hook_name]:
                del self._hooks[hook_name]

    def get_hooks(self, hook_name: str) -> list[HookEntry]:
        """Return registered entries for a hook (read-only copy)."""
        return list(self._hooks.get(hook_name, []))

    def list_hook_names(self) -> list[str]:
        """Return all registered hook names."""
        return sorted(self._hooks.keys())
