"""Recursive validation, freezing, and serialization of JSON-compatible values."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType


def freeze_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    selected = freeze_json(value, label)
    assert isinstance(selected, Mapping)
    return selected


def freeze_json(value: object, label: str) -> object:
    if value is None or isinstance(value, str | bool | int):
        selected = value
    elif isinstance(value, float):
        selected = _finite_number(value, label)
    elif isinstance(value, Mapping):
        selected = _freeze_object(value, label)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        selected = _freeze_array(value, label)
    else:
        raise TypeError(f"{label} must be JSON-compatible")
    return selected


def _finite_number(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} must contain only finite JSON numbers")
    return value


def _freeze_object(value: Mapping[object, object], label: str) -> Mapping[str, object]:
    frozen: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{label} object keys must be strings")
        frozen[key] = freeze_json(item, label)
    return MappingProxyType(frozen)


def _freeze_array(value: Sequence[object], label: str) -> tuple[object, ...]:
    return tuple(freeze_json(item, label) for item in value)


def thaw_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: thaw_json(item) for key, item in value.items()}


def thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return thaw_mapping(value)
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


__all__: list[str] = []
