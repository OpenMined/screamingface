"""Odoo-style class registry — register, extend, and resolve classes at runtime."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ClassEntry:
    """A mixin extension registered against a class key."""

    mixin: type
    plugin_name: str


@dataclass
class ClassRecord:
    """Tracks the base class and all mixin extensions for a given key."""

    base: type
    extensions: list[ClassEntry] = field(default_factory=list)
    _resolved: type | None = field(default=None, repr=False)


class ClassRegistry:
    """Register base classes under dotted keys, extend them with mixins, resolve final classes."""

    def __init__(self) -> None:
        self._classes: dict[str, ClassRecord] = {}

    def register(self, key: str, cls: type) -> None:
        """Register a base class under a dotted key (e.g. 'cache.CacheService')."""
        if key in self._classes:
            raise ValueError(f"Class key {key!r} is already registered")
        self._classes[key] = ClassRecord(base=cls)

    def extend(self, key: str, mixin: type, *, plugin_name: str = "") -> None:
        """Add a mixin extension to an existing class key.

        The mixin will be composed into the final class when `resolve()` is called.
        """
        record = self._classes.get(key)
        if record is None:
            raise KeyError(f"Class key {key!r} not registered — cannot extend")
        record.extensions.append(ClassEntry(mixin=mixin, plugin_name=plugin_name))
        record._resolved = None  # invalidate cache

    def resolve(self, key: str) -> type:
        """Build and return the final class by composing base + all mixin extensions.

        Uses `type()` to create a new class with proper MRO so `super()` works.
        """
        record = self._classes.get(key)
        if record is None:
            raise KeyError(f"Class key {key!r} not registered")

        if record._resolved is not None:
            return record._resolved

        if not record.extensions:
            record._resolved = record.base
        else:
            # Mixins listed last have highest priority (applied first in MRO)
            bases: tuple[type, ...] = tuple(e.mixin for e in record.extensions) + (record.base,)
            name = record.base.__name__
            record._resolved = type(name, bases, {})

        return record._resolved

    def unregister_plugin(self, plugin_name: str) -> None:
        """Remove all extensions registered by a plugin, invalidate resolved caches."""
        for record in self._classes.values():
            original_len = len(record.extensions)
            record.extensions = [e for e in record.extensions if e.plugin_name != plugin_name]
            if len(record.extensions) != original_len:
                record._resolved = None

    def list_keys(self) -> list[str]:
        """Return all registered class keys."""
        return sorted(self._classes.keys())

    def get_info(self, key: str) -> dict[str, Any]:
        """Return info about a class key for debugging."""
        record = self._classes.get(key)
        if record is None:
            raise KeyError(f"Class key {key!r} not registered")
        return {
            "key": key,
            "base": record.base.__name__,
            "extensions": [
                {"mixin": e.mixin.__name__, "plugin": e.plugin_name} for e in record.extensions
            ],
        }
