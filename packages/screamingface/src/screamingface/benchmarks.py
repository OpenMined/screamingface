"""Internal registered benchmark definitions over normalized evaluation cases."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from screamingface.data import load_live_questions, load_mock_questions
from screamingface.graders import _ExactChoiceGrader, _Grader

if TYPE_CHECKING:
    from screamingface.session import Session


@dataclass(frozen=True, slots=True)
class _EvaluationCase:
    """One fully prepared prompt and its hidden benchmark reference."""

    id: str
    prompt: str
    reference: object = field(repr=False)
    metadata_items: tuple[tuple[str, object], ...] = field(default=(), repr=False)

    @property
    def metadata(self) -> Mapping[str, object]:
        return MappingProxyType(dict(self.metadata_items))


@dataclass(frozen=True, slots=True)
class _LoadedBenchmark:
    """One materialized benchmark sample with dataset provenance."""

    definition: _BenchmarkDefinition
    cases: tuple[_EvaluationCase, ...]
    display_name: str
    dataset_source: str


type _BenchmarkLoader = Callable[["Session", int, int], _LoadedBenchmark]


@dataclass(frozen=True, slots=True)
class _BenchmarkDefinition:
    """A versioned dataset adapter paired with its official grading protocol."""

    id: str
    name: str
    version: str
    primary_metric: str
    grader: _Grader
    _loader: _BenchmarkLoader = field(repr=False)

    def load(self, session: Session, first: int, seed: int) -> _LoadedBenchmark:
        return self._loader(session, first, seed)


class _BenchmarkRegistry:
    def __init__(self, definitions: tuple[_BenchmarkDefinition, ...]) -> None:
        self._by_id = {definition.id: definition for definition in definitions}

    def get(self, benchmark_id: str) -> _BenchmarkDefinition:
        try:
            return self._by_id[benchmark_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._by_id))
            raise ValueError(
                f"unknown benchmark {benchmark_id!r}; available benchmarks: {available}"
            ) from exc


def _load_gpqa(session: Session, first: int, seed: int) -> _LoadedBenchmark:
    if session.mode == "mock":
        questions = load_mock_questions(first)
        display_name = "GPQA-shaped synthetic science fixture"
    else:
        questions = load_live_questions(first, seed)
        display_name = "GPQA Diamond"
    cases = tuple(
        _EvaluationCase(
            id=question.id,
            prompt=question.prompt(),
            reference=chr(65 + question.answer),
            metadata_items=(("subject", question.subject),),
        )
        for question in questions
    )
    return _LoadedBenchmark(
        definition=_GPQA,
        cases=cases,
        display_name=display_name,
        dataset_source=session.dataset_source,
    )


_GPQA = _BenchmarkDefinition(
    id="gpqa",
    name="GPQA Diamond",
    version="gpqa-diamond-v1",
    primary_metric="accuracy",
    grader=_ExactChoiceGrader(),
    _loader=_load_gpqa,
)

_BENCHMARKS = _BenchmarkRegistry((_GPQA,))


def _resolve_benchmark(benchmark_id: str) -> _BenchmarkDefinition:
    """Resolve a public string shorthand to its registered definition."""

    if not isinstance(benchmark_id, str) or not benchmark_id.strip():
        raise ValueError("benchmark must be a non-empty registered benchmark ID")
    return _BENCHMARKS.get(benchmark_id.strip().lower())
