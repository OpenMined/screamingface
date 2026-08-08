"""Client-independent values shared by Models and Fusions."""

from __future__ import annotations

import unicodedata
from abc import ABC, abstractmethod


class Recipe(ABC):
    """Non-constructible umbrella type for answer-producing Recipe values."""

    name: str

    @property
    @abstractmethod
    def _recipe_marker(self) -> None:
        """Keep Recipe non-constructible without adding public behavior."""


def _name(value: object, label: str) -> str:
    text = _text(value, label).strip()
    if any(unicodedata.category(char).startswith("C") for char in text):
        raise ValueError(f"{label} must not contain control characters")
    return text


def _model_route(value: object) -> str:
    return _name(value, "model route")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


__all__ = ["Recipe"]
