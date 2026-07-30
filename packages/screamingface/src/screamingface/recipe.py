"""Client-independent values shared by Models and Fusions."""

from __future__ import annotations

import math
import reprlib
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


def _instructions(value: object | None) -> str | None:
    if value is None:
        return None
    text = _text(value, "instructions")
    if not text.strip():
        raise ValueError("instructions must not be empty")
    return text


def _temperature(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("temperature must be a finite non-negative number")
    selected = float(value)
    if not math.isfinite(selected) or selected < 0:
        raise ValueError("temperature must be a finite non-negative number")
    return selected


def _reasoning(value: object | None) -> str | None:
    if value is None:
        return None
    return _name(value, "reasoning")


def _max_output_tokens(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("max_output_tokens must be a positive integer")
    if value < 1:
        raise ValueError("max_output_tokens must be a positive integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _model_value_repr(
    kind: str,
    *,
    model: str,
    name: str | None,
    instructions: str | None,
    temperature: float | None,
    reasoning: str | None,
    max_output_tokens: int | None,
) -> str:
    values = [repr(model)]
    if name is not None and name != model.rsplit("/", 1)[-1]:
        values.append(f"name={name!r}")
    if instructions is not None:
        values.append(f"instructions={reprlib.repr(instructions)}")
    if temperature is not None:
        values.append(f"temperature={temperature!r}")
    if reasoning is not None:
        values.append(f"reasoning={reasoning!r}")
    if max_output_tokens is not None:
        values.append(f"max_output_tokens={max_output_tokens}")
    return f"{kind}({', '.join(values)})"


__all__ = ["Recipe"]
