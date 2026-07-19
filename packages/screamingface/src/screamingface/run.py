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
            "members": {member_id: member._to_wire() for member_id, member in self._member_items},
            "answer": self.answer,
            "failure": None if self.failure is None else self.failure._to_wire(),
        }


@dataclass(frozen=True, slots=True, init=False)
class Run:
    """One immutable, in-memory Fusion run over a selected case sequence."""

    benchmark_id: str
    fusion_name: str
    fusion_url4: str
    case_ids: tuple[str, ...]
    results: tuple[CaseResult, ...]
    _member_items: tuple[tuple[str, str], ...] = field(repr=False)
    _benchmark: Benchmark = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        benchmark: Benchmark,
        fusion_name: str,
        fusion_url4: str,
        members: Mapping[str, str] | Sequence[tuple[str, str]],
        results: Sequence[CaseResult],
    ) -> None:
        if not isinstance(benchmark, Benchmark):
            raise TypeError("run benchmark must be an sf.Benchmark")
        normalized_name = _nonblank(fusion_name, "fusion name")
        recipe = _nonblank(fusion_url4, "fusion URL4")
        member_items = tuple(members.items()) if isinstance(members, Mapping) else tuple(members)
        _run_member_items(member_items)
        values = tuple(results)
        if not values:
            raise ValueError("a run requires at least one case result")
        if not all(isinstance(result, CaseResult) for result in values):
            raise TypeError("run results must be sf.CaseResult values")
        case_ids = tuple(result.case_id for result in values)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("run case IDs must be unique")
        _result_members(member_items, values)
        object.__setattr__(self, "benchmark_id", benchmark.id)
        object.__setattr__(self, "fusion_name", normalized_name)
        object.__setattr__(self, "fusion_url4", recipe)
        object.__setattr__(self, "case_ids", case_ids)
        object.__setattr__(self, "results", values)
        object.__setattr__(self, "_member_items", member_items)
        object.__setattr__(self, "_benchmark", benchmark)

    @property
    def members(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self._member_items))

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
            "fusion_name": self.fusion_name,
            "fusion_url4": self.fusion_url4,
            "members": dict(self._member_items),
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
    member_ids: list[str] = []
    for member_id, member in items:
        member_ids.append(_nonblank(member_id, "member slot ID"))
        if not isinstance(member, MemberResult):
            raise TypeError("result members must be sf.MemberResult values")
    if len(member_ids) != len(set(member_ids)):
        raise ValueError("result member slot IDs must be unique")


def _run_member_items(items: tuple[tuple[str, str], ...]) -> None:
    if len(items) < 2:
        raise ValueError("a run requires at least two member slots")
    expected = tuple(f"member_{position}" for position in range(1, len(items) + 1))
    observed: list[str] = []
    for member_id, model in items:
        observed.append(_nonblank(member_id, "run member slot ID"))
        _nonblank(model, "run member model")
    if tuple(observed) != expected:
        raise ValueError("run member slots must be contiguous member_1 through member_n")


def _result_members(members: tuple[tuple[str, str], ...], results: tuple[CaseResult, ...]) -> None:
    expected_ids = tuple(member_id for member_id, _ in members)
    expected_models = dict(members)
    for result in results:
        if result.failure is not None:
            continue
        if tuple(result.members) != expected_ids:
            raise ValueError("successful result member slots and order must match the Run")
        for member_id, member in result._member_items:
            if member.model != expected_models[member_id]:
                raise ValueError("successful result member models must match the Run")


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be blank")
    return value


__all__ = ["CaseResult", "FailureKind", "MemberResult", "Run", "RunFailure"]
