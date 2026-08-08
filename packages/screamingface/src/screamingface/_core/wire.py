"""Small, policy-free primitives for decoding external wire values."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import NoReturn, cast

type _Invalid = Callable[[str], NoReturn]


def mapping(value: object, label: str, invalid: _Invalid) -> Mapping[str, object]:
    """Return a JSON-like mapping or delegate the domain-specific failure."""

    if not isinstance(value, Mapping):
        invalid(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def text(value: object, label: str, invalid: _Invalid) -> str:
    """Return stripped non-blank wire text or delegate failure policy."""

    if not isinstance(value, str) or not value.strip():
        invalid(f"{label} must be non-blank text")
    return cast(str, value).strip()


__all__: list[str] = []
