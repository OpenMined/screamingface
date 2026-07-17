"""Internal answer-grading contracts and deterministic built-in graders."""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from screamingface.compiler import render_model_request
from screamingface.draco import (
    _axis_score,
    _criterion_judge_prompt,
    _DracoCriterion,
    _normalized_score,
    _parse_criterion_verdict,
    _pass_rate,
)

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

    async def grade_many(
        self,
        case: _EvaluationCase,
        answers: tuple[str, ...],
        *,
        engine: EnginePort,
    ) -> tuple[_Grade, ...]:
        """Grade related answers together so implementations can bound fan-out."""

        return tuple(
            await asyncio.gather(*(self.grade(case, answer, engine=engine) for answer in answers))
        )


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


@dataclass(frozen=True, slots=True)
class _DracoRubricGrader(_Grader):
    """Grade open-ended DRACO answers with URL4-routed per-criterion judges."""

    judge_model: str = "google/gemini-3.1-pro-preview"
    judge_runs: int = 5
    max_concurrency: int = 8

    @property
    def name(self) -> str:
        return "draco_rubric"

    def parse_answer(self, text: str) -> str:
        return text.strip()

    async def grade(
        self,
        case: _EvaluationCase,
        answer: str,
        *,
        engine: EnginePort,
    ) -> _Grade:
        return await self._grade_answer(
            case, answer, engine=engine, semaphore=asyncio.Semaphore(self.max_concurrency)
        )

    async def grade_many(
        self,
        case: _EvaluationCase,
        answers: tuple[str, ...],
        *,
        engine: EnginePort,
    ) -> tuple[_Grade, ...]:
        semaphore = asyncio.Semaphore(self.max_concurrency)
        return tuple(
            await asyncio.gather(
                *(
                    self._grade_answer(case, answer, engine=engine, semaphore=semaphore)
                    for answer in answers
                )
            )
        )

    async def _grade_answer(
        self,
        case: _EvaluationCase,
        answer: str,
        *,
        engine: EnginePort,
        semaphore: asyncio.Semaphore,
    ) -> _Grade:
        parsed = self.parse_answer(answer)
        if not parsed:
            return _Grade(
                answer="",
                score=0.0,
                metrics=_empty_draco_metrics(),
                failure_code="invalid_answer",
                failure_message="Model did not return a research response",
            )
        criteria = _case_criteria(case)
        configured_runs = case.metadata.get("judge_runs", self.judge_runs)
        runs = configured_runs if isinstance(configured_runs, int) else self.judge_runs
        tasks = (
            self._judge_criterion(
                case,
                parsed,
                criterion,
                engine=engine,
                semaphore=semaphore,
            )
            for _run in range(max(1, runs))
            for criterion in criteria
        )
        raw_verdicts = await asyncio.gather(*tasks, return_exceptions=True)
        per_run: list[dict[str, bool]] = []
        width = len(criteria)
        for offset in range(0, len(raw_verdicts), width):
            verdicts: dict[str, bool] = {}
            for criterion, verdict in zip(
                criteria, raw_verdicts[offset : offset + width], strict=True
            ):
                if isinstance(verdict, bool):
                    verdicts[criterion.id] = verdict
            if verdicts:
                per_run.append(verdicts)
        if not per_run:
            return _Grade(
                answer=parsed,
                score=0.0,
                metrics=_empty_draco_metrics(),
                failure_code="invalid_judge_result",
                failure_message="DRACO judge produced no valid criterion verdicts",
            )
        scores = tuple(_normalized_score(criteria, verdicts) for verdicts in per_run)
        pass_rates = tuple(_pass_rate(criteria, verdicts) for verdicts in per_run)
        coverage = tuple(len(verdicts) / len(criteria) for verdicts in per_run)
        factual = tuple(_axis_score(criteria, verdicts, "factual-accuracy") for verdicts in per_run)
        score = sum(scores) / len(scores)
        return _Grade(
            answer=parsed,
            score=score,
            metrics=(
                ("normalized_score", score),
                ("pass_rate", sum(pass_rates) / len(pass_rates)),
                ("factual_accuracy", sum(factual) / len(factual)),
                ("verdict_coverage", sum(coverage) / len(coverage)),
            ),
        )

    async def _judge_criterion(
        self,
        case: _EvaluationCase,
        answer: str,
        criterion: _DracoCriterion,
        *,
        engine: EnginePort,
        semaphore: asyncio.Semaphore,
    ) -> bool | None:
        prompt = _criterion_judge_prompt(
            question=case.prompt,
            answer=answer,
            criterion=criterion,
        )
        expression = render_model_request(
            model=self.judge_model,
            prompt=prompt,
            params={"temperature": 0.2, "max_tokens": 128},
        )
        async with semaphore:
            body = await engine.evaluate(expression)
        return _parse_criterion_verdict(body)


def _case_criteria(case: _EvaluationCase) -> tuple[_DracoCriterion, ...]:
    reference = case.reference
    if not isinstance(reference, tuple) or not all(
        isinstance(criterion, _DracoCriterion) for criterion in reference
    ):
        raise TypeError("DRACO evaluation case has an invalid rubric reference")
    return reference


def _empty_draco_metrics() -> tuple[tuple[str, float], ...]:
    return (
        ("normalized_score", 0.0),
        ("pass_rate", 0.0),
        ("factual_accuracy", 0.0),
        ("verdict_coverage", 0.0),
    )
