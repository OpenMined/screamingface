"""Lifecycle owner for the built-in taxonomy feature plugin."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...core.usage_accounting.hooks import build_accounting_handler
from .settings import TaxonomyPluginSettings

__all__ = ["TaxonomyPlugin"]


class TaxonomyHandler(Protocol):
    async def close(self) -> None: ...


class TaxonomyPlugin:
    """Default-enabled non-provider feature with app-lifetime observer ownership."""

    def __init__(self, settings: TaxonomyPluginSettings | None = None) -> None:
        self._enabled = (settings or TaxonomyPluginSettings()).enabled
        self.handler: TaxonomyHandler | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def sanitize_provider_response(payload: object) -> object:
        """Remove the gateway-reserved namespace from untrusted provider/cache JSON."""
        if not isinstance(payload, dict):
            return payload
        # INVARIANT: provider-returned dict subclasses cannot execute overrides here.
        # The provider call may already be billed, so sanitization must not turn its
        # successful response into a local failure.
        sanitized = dict.copy(payload)
        if "_aigw" not in sanitized:
            return payload
        sanitized.pop("_aigw", None)
        return sanitized

    def start(
        self,
        build_handler: Callable[[], TaxonomyHandler] = build_accounting_handler,
    ) -> TaxonomyHandler | None:
        """Create the observer once when this feature is enabled."""
        if not self.enabled:
            return None
        if self.handler is None:
            self.handler = build_handler()
        return self.handler

    async def close(self) -> None:
        """Drop and close the observer so no request can reuse a closing pool."""
        handler = self.handler
        self.handler = None
        if handler is not None:
            await handler.close()
