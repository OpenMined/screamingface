"""Internal answer-grading contracts and deterministic built-in graders."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from screamingface.benchmarks import _EvaluationCase
    from screamingface.engine import EnginePort

_CHOICE = re.compile(r"\b([A-D])\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _Grade:
    """One grader's result for one completed answer."""

    answer: str
    score: float
    metrics: tuple[tuple[str, float], ...]
    failure_code: str | None = None
    failure_message: str | None = None

    @property
    def valid(self) -> bool:
        return self.failure_code is None


class _Grader(ABC):
    """Internal contract for interpreting and grading completed answers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable grader identity recorded by its benchmark definition."""

    @abstractmethod
    def parse_answer(self, text: str) -> str:
        """Convert raw model output into the benchmark's answer representation."""

    @abstractmethod
    async def grade(
        self,
        case: _EvaluationCase,
        answer: str,
        *,
        engine: EnginePort,
    ) -> _Grade:
        """Grade one completed answer, using the engine only when required."""


class _ExactChoiceGrader(_Grader):
    """Grade an A-D answer against a hidden reference letter."""

    @property
    def name(self) -> str:
        return "exact_choice"

    def parse_answer(self, text: str) -> str:
        match = _CHOICE.search(text.strip())
        return match.group(1).upper() if match else ""

    async def grade(
        self,
        case: _EvaluationCase,
        answer: str,
        *,
        engine: EnginePort,
    ) -> _Grade:
        del engine
        parsed = self.parse_answer(answer)
        if not parsed:
            return _Grade(
                answer="",
                score=0.0,
                metrics=(("accuracy", 0.0),),
                failure_code="invalid_answer",
                failure_message="Model did not return A-D",
            )
        score = float(parsed == case.reference)
        return _Grade(
            answer=parsed,
            score=score,
            metrics=(("accuracy", score),),
        )
