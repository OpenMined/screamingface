from __future__ import annotations

from .plugin_base import ProviderPluginBase


class ProviderRegistry:
    """Lookup from `custom_llm_provider` to provider plugin."""

    def __init__(self) -> None:
        self._plugins: dict[str, ProviderPluginBase] = {}

    def register(self, plugin: ProviderPluginBase) -> None:
        if plugin.custom_llm_provider in self._plugins:
            raise ValueError(
                f"duplicate provider plugin for '{plugin.custom_llm_provider}': "
                f"{type(self._plugins[plugin.custom_llm_provider]).__name__} vs "
                f"{type(plugin).__name__}"
            )
        self._plugins[plugin.custom_llm_provider] = plugin

    def get(self, custom_llm_provider: str) -> ProviderPluginBase | None:
        return self._plugins.get(custom_llm_provider)

    def all(self) -> list[ProviderPluginBase]:
        return list(self._plugins.values())
