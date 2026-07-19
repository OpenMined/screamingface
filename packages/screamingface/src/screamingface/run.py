"""Immutable public records produced by the Fusion run stage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from screamingface.benchmark import Benchmark

if TYPE_CHECKING:
    from screamingface.grades import Grades

type FailureKind = Literal["connection", "timeout", "http", "url4", "protocol"]
_FAILURE_KINDS = frozenset({"connection", "timeout", "http", "url4", "protocol"})


@dataclass(frozen=True, slots=True)
class MemberResult:
    """One resolved member model and its exact answer text."""

    model: str
    answer: str

    def __post_init__(self) -> None:
        _nonblank(self.model, "member model")
        _nonblank(self.answer, "member answer")

    def _to_wire(self) -> dict[str, str]:
        return {"model": self.model, "answer": self.answer}


@dataclass(frozen=True, slots=True)
class RunFailure:
    """One safe, serializable case-execution failure."""

    case_id: str
    kind: FailureKind
    message: str
    status: int | None = None
    code: str | None = None

    def __post_init__(self) -> None:
        _nonblank(self.case_id, "failure case ID")
        if self.kind not in _FAILURE_KINDS:
            raise ValueError(f"unknown run failure kind {self.kind!r}")
        _nonblank(self.message, "failure message")
        if self.status is not None and (
            isinstance(self.status, bool)
            or not isinstance(self.status, int)
            or not 100 <= self.status <= 599
        ):
            raise ValueError("failure status must be an HTTP status or None")
        if self.code is not None:
            _nonblank(self.code, "failure code")

    def _to_wire(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "message": self.message,
            "status": self.status,
            "code": self.code,
        }


@dataclass(frozen=True, slots=True, init=False)
class CaseResult:
    """The atomic success or failure of one selected benchmark case."""

    case_id: str
    answer: str | None
    failure: RunFailure | None
    _member_items: tuple[tuple[str, MemberResult], ...] = field(repr=False)

    def __init__(
        self,
        case_id: str,
        *,
        members: Mapping[str, MemberResult] | Sequence[tuple[str, MemberResult]],
        answer: str | None,
        failure: RunFailure | None = None,
    ) -> None:
        normalized_id = _nonblank(case_id, "result case ID")
        items = tuple(members.items()) if isinstance(members, Mapping) else tuple(members)
        _member_items(items)
        if failure is None:
            if not items:
                raise ValueError("a successful case result requires members")
            normalized_answer: str | None = _nonblank(answer, "fusion answer")
        else:
            if failure.case_id != normalized_id:
                raise ValueError("result and failure case IDs must match")
            if items or answer is not None:
                raise ValueError("a failed case result cannot contain partial answers")
            normalized_answer = None
        object.__setattr__(self, "case_id", normalized_id)
        object.__setattr__(self, "answer", normalized_answer)
        object.__setattr__(self, "failure", failure)
        object.__setattr__(self, "_member_items", items)

    @property
    def members(self) -> Mapping[str, MemberResult]:
        return MappingProxyType(dict(self._member_items))

    def _to_wire(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "members": {panel_id: member._to_wire() for panel_id, member in self._member_items},
            "answer": self.answer,
            "failure": None if self.failure is None else self.failure._to_wire(),
        }


@dataclass(frozen=True, slots=True, init=False)
class Run:
    """One immutable, in-memory Fusion run over a selected case sequence."""

    benchmark_id: str
    fusion_url4: str
    case_ids: tuple[str, ...]
    results: tuple[CaseResult, ...]
    _benchmark: Benchmark = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        benchmark: Benchmark,
        fusion_url4: str,
        results: Sequence[CaseResult],
    ) -> None:
        if not isinstance(benchmark, Benchmark):
            raise TypeError("run benchmark must be an sf.Benchmark")
        recipe = _nonblank(fusion_url4, "fusion URL4")
        values = tuple(results)
        if not values:
            raise ValueError("a run requires at least one case result")
        if not all(isinstance(result, CaseResult) for result in values):
            raise TypeError("run results must be sf.CaseResult values")
        case_ids = tuple(result.case_id for result in values)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("run case IDs must be unique")
        object.__setattr__(self, "benchmark_id", benchmark.id)
        object.__setattr__(self, "fusion_url4", recipe)
        object.__setattr__(self, "case_ids", case_ids)
        object.__setattr__(self, "results", values)
        object.__setattr__(self, "_benchmark", benchmark)

    @property
    def failures(self) -> tuple[RunFailure, ...]:
        return tuple(result.failure for result in self.results if result.failure is not None)

    @property
    def complete(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, object]:
        """Return the complete public run record as JSON-compatible values."""

        return {
            "benchmark_id": self.benchmark_id,
            "fusion_url4": self.fusion_url4,
            "case_ids": list(self.case_ids),
            "results": [result._to_wire() for result in self.results],
            "failures": [failure._to_wire() for failure in self.failures],
            "complete": self.complete,
        }

    def grade(self) -> Grades:
        """Grade the captured Fusion and member answers without rerunning them."""

        from screamingface._grading import grade_run

        return grade_run(self)


def _member_items(items: tuple[tuple[str, MemberResult], ...]) -> None:
    panel_ids: list[str] = []
    for panel_id, member in items:
        panel_ids.append(_nonblank(panel_id, "member slot ID"))
        if not isinstance(member, MemberResult):
            raise TypeError("result members must be sf.MemberResult values")
    if len(panel_ids) != len(set(panel_ids)):
        raise ValueError("result member slot IDs must be unique")


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be blank")
    return value


__all__ = ["CaseResult", "FailureKind", "MemberResult", "Run", "RunFailure"]
