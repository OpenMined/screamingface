"""Fusion reduction strategy values."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from screamingface.recipe import (
    _instructions,
    _max_output_tokens,
    _model_route,
    _model_value_repr,
    _reasoning,
    _temperature,
)


class Reducer(ABC):
    """Non-constructible umbrella type for Fusion reduction strategies."""

    kind: ClassVar[str]

    @property
    @abstractmethod
    def _reducer_marker(self) -> None:
        """Keep Reducer non-constructible without adding public behavior."""


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Synthesis(Reducer):
    """Use one model operation to synthesize ordered Fusion member answers."""

    model: str
    instructions: str | None
    temperature: float | None
    reasoning: str | None
    max_output_tokens: int | None
    kind: ClassVar[str] = "synthesis"

    def __init__(
        self,
        model: str,
        *,
        instructions: str | None = None,
        temperature: float | None = None,
        reasoning: str | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        object.__setattr__(self, "model", _model_route(model))
        object.__setattr__(self, "instructions", _instructions(instructions))
        object.__setattr__(self, "temperature", _temperature(temperature))
        object.__setattr__(self, "reasoning", _reasoning(reasoning))
        object.__setattr__(self, "max_output_tokens", _max_output_tokens(max_output_tokens))

    @property
    def _reducer_marker(self) -> None:
        return None

    def __repr__(self) -> str:
        return _model_value_repr(
            "Synthesis",
            model=self.model,
            name=None,
            instructions=self.instructions,
            temperature=self.temperature,
            reasoning=self.reasoning,
            max_output_tokens=self.max_output_tokens,
        )


__all__ = ["Reducer", "Synthesis"]
