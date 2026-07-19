"""Immutable public records produced by benchmark grading."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from screamingface.graders import ExactChoice, Grader, Rubric
from screamingface.run import Run, RunFailure

type GradeFailureKind = Literal[
    "connection",
    "timeout",
    "http",
    "url4",
    "protocol",
    "invalid_judge_output",
    "incomplete_verdicts",
]
type CriterionStatus = Literal["MET", "UNMET"]
type GradingFailure = RunFailure | GradeFailure

_GRADE_FAILURE_KINDS = frozenset(
    {
        "connection",
        "timeout",
        "http",
        "url4",
        "protocol",
        "invalid_judge_output",
        "incomplete_verdicts",
    }
)
_CRITERION_STATUSES = frozenset({"MET", "UNMET"})


@dataclass(frozen=True, slots=True)
class GradeFailure:
    """One safe, serializable grading failure for a target or verdict."""

    case_id: str
    target: str
    kind: GradeFailureKind
    message: str
    criterion_id: str | None = None
    pass_number: int | None = None
    status: int | None = None
    code: str | None = None

    def __post_init__(self) -> None:
        _nonblank(self.case_id, "grade failure case ID")
        _nonblank(self.target, "grade failure target")
        if self.kind not in _GRADE_FAILURE_KINDS:
            raise ValueError(f"unknown grade failure kind {self.kind!r}")
        _nonblank(self.message, "grade failure message")
        if (self.criterion_id is None) != (self.pass_number is None):
            raise ValueError("grade failure criterion ID and pass number must be set together")
        if self.criterion_id is not None:
            _nonblank(self.criterion_id, "grade failure criterion ID")
            _positive_int(self.pass_number, "grade failure pass number")
        if self.status is not None and (
            isinstance(self.status, bool)
            or not isinstance(self.status, int)
            or not 100 <= self.status <= 599
        ):
            raise ValueError("grade failure status must be an HTTP status or None")
        if self.code is not None:
            _nonblank(self.code, "grade failure code")

    def _to_wire(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "target": self.target,
            "kind": self.kind,
            "message": self.message,
            "criterion_id": self.criterion_id,
            "pass_number": self.pass_number,
            "status": self.status,
            "code": self.code,
        }


@dataclass(frozen=True, slots=True)
class CriterionVerdict:
    """One rubric criterion/pass outcome with its complete judge evidence."""

    criterion_id: str
    section: str
    requirement: str
    weight: float
    pass_number: int
    status: CriterionStatus | None
    explanation: str | None
    raw_response: str | None
    failure: GradeFailure | None = None

    def __post_init__(self) -> None:
        _nonblank(self.criterion_id, "criterion ID")
        _nonblank(self.section, "criterion section")
        _nonblank(self.requirement, "criterion requirement")
        object.__setattr__(self, "weight", _finite_nonzero(self.weight, "criterion weight"))
        _positive_int(self.pass_number, "criterion pass number")
        if self.failure is None:
            if self.status not in _CRITERION_STATUSES:
                raise ValueError("a successful verdict status must be MET or UNMET")
            _nonblank(self.explanation, "criterion explanation")
            _nonblank(self.raw_response, "criterion raw response")
        else:
            if not isinstance(self.failure, GradeFailure):
                raise TypeError("criterion failure must be an sf.GradeFailure")
            if self.status is not None:
                raise ValueError("a failed verdict cannot contain a status")
            if self.failure.criterion_id != self.criterion_id:
                raise ValueError("verdict and failure criterion IDs must match")
            if self.failure.pass_number != self.pass_number:
                raise ValueError("verdict and failure pass numbers must match")
            _optional_nonblank(self.explanation, "criterion explanation")
            _optional_nonblank(self.raw_response, "criterion raw response")

    def _to_wire(self) -> dict[str, object]:
        return {
            "criterion_id": self.criterion_id,
            "section": self.section,
            "requirement": self.requirement,
            "weight": self.weight,
            "pass_number": self.pass_number,
            "status": self.status,
            "explanation": self.explanation,
            "raw_response": self.raw_response,
            "failure": None if self.failure is None else self.failure._to_wire(),
        }


@dataclass(frozen=True, slots=True, init=False)
class Grade:
    """One immutable Fusion or member grade for a single case."""

    score: float | None
    coverage: float
    verdicts: tuple[CriterionVerdict, ...]
    failure: GradeFailure | None
    _metric_items: tuple[tuple[str, float], ...] = field(repr=False)

    def __init__(
        self,
        *,
        score: float | None,
        metrics: Mapping[str, float],
        coverage: float,
        verdicts: Sequence[CriterionVerdict] = (),
        failure: GradeFailure | None = None,
    ) -> None:
        normalized_score = None if score is None else _unit_float(score, "grade score")
        normalized_coverage = _unit_float(coverage, "grade coverage")
        metric_items = _metrics(metrics)
        normalized_verdicts = tuple(verdicts)
        if not all(isinstance(verdict, CriterionVerdict) for verdict in normalized_verdicts):
            raise TypeError("grade verdicts must be sf.CriterionVerdict values")
        if failure is not None and not isinstance(failure, GradeFailure):
            raise TypeError("grade failure must be an sf.GradeFailure or None")
        _grade_state(
            normalized_score,
            normalized_coverage,
            metric_items,
            normalized_verdicts,
            failure,
        )
        object.__setattr__(self, "score", normalized_score)
        object.__setattr__(self, "coverage", normalized_coverage)
        object.__setattr__(self, "verdicts", normalized_verdicts)
        object.__setattr__(self, "failure", failure)
        object.__setattr__(self, "_metric_items", metric_items)

    @property
    def metrics(self) -> Mapping[str, float]:
        return MappingProxyType(dict(self._metric_items))

    @property
    def valid(self) -> bool:
        return self.score is not None

    def _to_wire(self) -> dict[str, object]:
        return {
            "score": self.score,
            "metrics": dict(self._metric_items),
            "coverage": self.coverage,
            "verdicts": [verdict._to_wire() for verdict in self.verdicts],
            "failure": None if self.failure is None else self.failure._to_wire(),
            "valid": self.valid,
        }


@dataclass(frozen=True, slots=True, init=False)
class CaseGrades:
    """Fusion and member grades, or the run failure, for one selected case."""

    case_id: str
    fusion: Grade | None
    run_failure: RunFailure | None
    _member_items: tuple[tuple[str, Grade], ...] = field(repr=False)

    def __init__(
        self,
        case_id: str,
        *,
        fusion: Grade | None,
        members: Mapping[str, Grade] | Sequence[tuple[str, Grade]],
        run_failure: RunFailure | None = None,
    ) -> None:
        normalized_id = _nonblank(case_id, "case grade ID")
        items = tuple(members.items()) if isinstance(members, Mapping) else tuple(members)
        _grade_members(items)
        if run_failure is None:
            if not isinstance(fusion, Grade):
                raise TypeError("a successful case grade requires an sf.Grade Fusion value")
            if not items:
                raise ValueError("a successful case grade requires member grades")
        else:
            if not isinstance(run_failure, RunFailure):
                raise TypeError("case run failure must be an sf.RunFailure")
            if run_failure.case_id != normalized_id:
                raise ValueError("case grade and run failure IDs must match")
            if fusion is not None or items:
                raise ValueError("a failed case grade cannot contain Fusion or member grades")
        object.__setattr__(self, "case_id", normalized_id)
        object.__setattr__(self, "fusion", fusion)
        object.__setattr__(self, "run_failure", run_failure)
        object.__setattr__(self, "_member_items", items)

    @property
    def members(self) -> Mapping[str, Grade]:
        return MappingProxyType(dict(self._member_items))

    def _to_wire(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "fusion": None if self.fusion is None else self.fusion._to_wire(),
            "members": {target: grade._to_wire() for target, grade in self._member_items},
            "run_failure": (None if self.run_failure is None else self.run_failure._to_wire()),
        }


@dataclass(frozen=True, slots=True, init=False)
class Grades:
    """One immutable, in-memory grading artifact derived from a Run."""

    benchmark_id: str
    fusion_url4: str
    grader: Grader
    case_ids: tuple[str, ...]
    results: tuple[CaseGrades, ...]
    _run: Run = field(repr=False, compare=False)

    def __init__(self, *, run: Run, results: Sequence[CaseGrades]) -> None:
        if not isinstance(run, Run):
            raise TypeError("grades run must be an sf.Run")
        values = tuple(results)
        if not all(isinstance(result, CaseGrades) for result in values):
            raise TypeError("grade results must be sf.CaseGrades values")
        _grade_results(run, values)
        object.__setattr__(self, "benchmark_id", run.benchmark_id)
        object.__setattr__(self, "fusion_url4", run.fusion_url4)
        object.__setattr__(self, "grader", run._benchmark.grader)
        object.__setattr__(self, "case_ids", run.case_ids)
        object.__setattr__(self, "results", values)
        object.__setattr__(self, "_run", run)

    @property
    def failures(self) -> tuple[GradingFailure, ...]:
        failures: list[GradingFailure] = []
        for case in self.results:
            if case.run_failure is not None:
                failures.append(case.run_failure)
                continue
            assert case.fusion is not None
            for grade in (case.fusion, *(grade for _, grade in case._member_items)):
                failures.extend(
                    verdict.failure for verdict in grade.verdicts if verdict.failure is not None
                )
                if grade.failure is not None:
                    failures.append(grade.failure)
        return tuple(failures)

    @property
    def complete(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, object]:
        """Return the complete public grading record as JSON-compatible values."""

        return {
            "benchmark_id": self.benchmark_id,
            "fusion_url4": self.fusion_url4,
            "grader": _grader_wire(self.grader),
            "case_ids": list(self.case_ids),
            "results": [result._to_wire() for result in self.results],
            "failures": [_failure_wire(failure) for failure in self.failures],
            "complete": self.complete,
        }


def _grade_state(
    score: float | None,
    coverage: float,
    metrics: tuple[tuple[str, float], ...],
    verdicts: tuple[CriterionVerdict, ...],
    failure: GradeFailure | None,
) -> None:
    if verdicts:
        _verdict_coverage(coverage, verdicts)
    if failure is None:
        _valid_grade_state(score, coverage, verdicts)
        return
    _failed_grade_state(score, coverage, metrics)


def _verdict_coverage(coverage: float, verdicts: tuple[CriterionVerdict, ...]) -> None:
    observed = sum(verdict.status is not None for verdict in verdicts) / len(verdicts)
    if not math.isclose(coverage, observed, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("grade coverage must match resolved verdict coverage")


def _valid_grade_state(
    score: float | None, coverage: float, verdicts: tuple[CriterionVerdict, ...]
) -> None:
    if score is None:
        raise ValueError("a valid grade requires a score")
    if coverage != 1.0:
        raise ValueError("a valid grade requires complete coverage")
    if any(verdict.failure is not None for verdict in verdicts):
        raise ValueError("a valid grade cannot contain failed verdicts")


def _failed_grade_state(
    score: float | None, coverage: float, metrics: tuple[tuple[str, float], ...]
) -> None:
    if score is not None:
        raise ValueError("a failed grade cannot contain a score")
    if coverage == 1.0:
        raise ValueError("a failed grade cannot have complete coverage")
    if metrics:
        raise ValueError("a failed grade cannot publish partial metrics")


def _metrics(values: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    if not isinstance(values, Mapping):
        raise TypeError("grade metrics must be a mapping")
    return tuple(
        (_nonblank(key, "grade metric name"), _unit_float(value, f"grade metric {key!r}"))
        for key, value in values.items()
    )


def _grade_members(items: tuple[tuple[str, Grade], ...]) -> None:
    targets: list[str] = []
    for target, grade in items:
        targets.append(_nonblank(target, "grade member target"))
        if not isinstance(grade, Grade):
            raise TypeError("case member grades must be sf.Grade values")
    if len(targets) != len(set(targets)):
        raise ValueError("case member grade targets must be unique")


def _grade_results(run: Run, values: tuple[CaseGrades, ...]) -> None:
    if tuple(result.case_id for result in values) != run.case_ids:
        raise ValueError("grade case IDs and order must match the Run")
    for run_result, grades in zip(run.results, values, strict=True):
        if run_result.failure is not None:
            if grades.run_failure != run_result.failure:
                raise ValueError("case grade run failure must match the Run")
            continue
        if grades.run_failure is not None:
            raise ValueError("a successful Run result cannot become a failed case grade")
        if tuple(grades.members) != tuple(run_result.members):
            raise ValueError("grade member slots and order must match the Run")
        assert grades.fusion is not None
        _grade_identity(grades.case_id, "fusion", grades.fusion)
        for target, grade in grades._member_items:
            _grade_identity(grades.case_id, target, grade)


def _grade_identity(case_id: str, target: str, grade: Grade) -> None:
    failures = [
        *(verdict.failure for verdict in grade.verdicts if verdict.failure is not None),
        *(() if grade.failure is None else (grade.failure,)),
    ]
    for failure in failures:
        if failure.case_id != case_id or failure.target != target:
            raise ValueError("grade failure identity must match its case and target")


def _grader_wire(grader: Grader) -> dict[str, object]:
    if isinstance(grader, ExactChoice):
        return {"type": grader.kind}
    if isinstance(grader, Rubric):
        return {
            "type": grader.kind,
            "model": grader.model,
            "prompt": grader.prompt,
            "passes": grader.passes,
            "params": grader.params,
        }
    raise TypeError(f"unsupported grader {type(grader).__name__!r}")


def _failure_wire(failure: GradingFailure) -> dict[str, object]:
    return failure._to_wire()


def _unit_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{label} must be finite and between 0 and 1")
    return normalized


def _finite_nonzero(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized == 0.0:
        raise ValueError(f"{label} must be finite and non-zero")
    return normalized


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _optional_nonblank(value: object, label: str) -> None:
    if value is not None:
        _nonblank(value, label)


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be blank")
    return value


__all__ = [
    "CaseGrades",
    "CriterionVerdict",
    "Grade",
    "GradeFailure",
    "GradeFailureKind",
    "Grades",
]
