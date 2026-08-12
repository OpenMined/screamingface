"""Client-independent values shared by composable Candidate Recipes."""

from __future__ import annotations

import unicodedata
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from screamingface.pipeline import Pipeline


class Recipe(ABC):
    """Non-constructible umbrella type for answer-producing Recipe values."""

    name: str

    def then(self, next_recipe: str | Recipe) -> Pipeline:
        """Return an immutable serial Pipeline ending in ``next_recipe``."""

        from screamingface.pipeline import Pipeline

        selected = _recipe(next_recipe, "Pipeline stage")
        before = self.stages if isinstance(self, Pipeline) and not self._is_named else (self,)
        after = (
            selected.stages
            if isinstance(selected, Pipeline) and not selected._is_named
            else (selected,)
        )
        return Pipeline((*before, *after))

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


def _recipe(value: object, label: str) -> Recipe:
    """Normalize the one intentional shorthand at every Recipe-valued position."""

    if isinstance(value, str):
        from screamingface.model import Model

        return Model(value)
    if not _is_supported_recipe(value):
        raise TypeError(f"{label} must be a model route or sf.Model, sf.Fusion, or sf.Pipeline")
    assert isinstance(value, Recipe)
    return value


def _is_supported_recipe(value: object) -> bool:
    from screamingface.fusion import Fusion
    from screamingface.model import Model
    from screamingface.pipeline import Pipeline

    return isinstance(value, Model | Fusion | Pipeline)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


__all__ = ["Recipe"]
