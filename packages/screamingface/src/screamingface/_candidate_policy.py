"""Validated immutable Candidate generation overrides."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType

type GenerationScalar = str | int | float | bool
type GenerationParams = Mapping[str, GenerationScalar]

_EXECUTION_OWNED_PARAMS = frozenset(
    {
        "input",
        "messages",
        "model",
        "plugins",
        "provider",
        "q",
        "stream",
        "tool_choice",
        "tools",
        "web_search",
        "web_search_exclude",
        "web_search_excluded_domains",
        "web_search_policy",
    }
)
"""Transport, routing, tool, and Benchmark protocol fields users cannot override."""


def prompt(value: object | None, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string or None")
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def params(value: object | None, label: str) -> GenerationParams:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping or None")
    selected: dict[str, GenerationScalar] = {}
    for name, item in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{label} names must be non-empty strings")
        if name in _EXECUTION_OWNED_PARAMS:
            raise ValueError(
                f"{label} parameter {name!r} is reserved for Benchmark and Engine execution"
            )
        if not isinstance(item, str | int | float | bool):
            raise TypeError(f"{label} value {name!r} must be a scalar")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"{label} value {name!r} must be finite")
        selected[name] = item
    return MappingProxyType(selected)


__all__: list[str] = []
