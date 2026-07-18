"""Grader definitions; grading execution is introduced in Phase 3."""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

from screamingface.model_inputs import ParameterValue, make_model_call


class Grader(ABC):
    """Base type for benchmark answer grading strategies."""

    kind: ClassVar[str]


@dataclass(frozen=True, slots=True)
class ExactChoice(Grader):
    """Compare one normalized answer choice with the sealed reference."""

    kind: ClassVar[str] = "exact_choice"


@dataclass(frozen=True, slots=True, init=False)
class Rubric(Grader):
    """Judge each rubric criterion through an advertised model route."""

    model: str
    prompt: str
    passes: int
    _parameter_items: tuple[tuple[str, ParameterValue], ...] = field(repr=False)
    kind: ClassVar[str] = "rubric"

    def __init__(
        self,
        *,
        model: str,
        prompt: str,
        passes: int = 1,
        params: Mapping[str, ParameterValue] | None = None,
    ) -> None:
        if isinstance(passes, bool) or not isinstance(passes, int) or passes < 1:
            raise ValueError("rubric passes must be a positive integer")
        call = make_model_call(model=model, prompt=prompt, params=params)
        object.__setattr__(self, "model", call.model)
        object.__setattr__(self, "prompt", call.prompt)
        object.__setattr__(self, "passes", passes)
        object.__setattr__(self, "_parameter_items", call.parameter_items)

    @property
    def params(self) -> dict[str, ParameterValue]:
        return dict(self._parameter_items)
