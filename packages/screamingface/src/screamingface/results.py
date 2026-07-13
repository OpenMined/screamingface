"""Run results and metrics (engine-side).

A `RunResult` captures everything about one evaluation: the per-question
breakdown, per-model accuracy/latency/cost, and the headline fusion metrics —
crucially **gain over the best single model**, the number a fusion researcher
actually cares about.
"""

from __future__ import annotations

from dataclasses import dataclass

from .datasets import Question
from .engine import Answer


@dataclass
class QuestionResult:
    question: Question
    model_answers: list[Answer]  # aligned with the fusion's slots
    final_choice: str
    final_text: str
    correct: bool
    note: str  # how the answer was reduced
    reasoning: str  # synthesized reduce reasoning


@dataclass
class ModelResult:
    model_id: str
    model_label: str
    color: str
    n: int
    n_correct: int
    mean_latency_ms: float
    total_cost: float

    @property
    def accuracy(self) -> float:
        return 100.0 * self.n_correct / self.n if self.n else 0.0


@dataclass
class RunResult:
    fusion_name: str
    model_ids: list[str]
    model_labels: list[str]
    reduce_label: str
    loop_label: str
    judge_id: str | None
    benchmark_id: str
    benchmark_name: str
    seed: int
    sample_size: int
    source: str
    question_results: list[QuestionResult]
    model_results: list[ModelResult]

    @property
    def n(self) -> int:
        return len(self.question_results)

    @property
    def n_correct(self) -> int:
        return sum(1 for q in self.question_results if q.correct)

    @property
    def score(self) -> float:
        """Fusion accuracy, percent."""
        return 100.0 * self.n_correct / self.n if self.n else 0.0

    @property
    def baseline(self) -> float:
        """Best single-model accuracy — the bar the fusion must beat."""
        return max((m.accuracy for m in self.model_results), default=0.0)

    @property
    def gain_over_best(self) -> float:
        return self.score - self.baseline

    @property
    def total_cost(self) -> float:
        return sum(m.total_cost for m in self.model_results)

    def __repr__(self) -> str:
        return (
            f"RunResult({self.fusion_name!r} on {self.benchmark_name!r}: "
            f"score={self.score:.1f}  baseline={self.baseline:.1f}  "
            f"gain={self.gain_over_best:+.1f})"
        )
