"""Immutable public summaries produced by benchmark aggregation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

type FailureKind = Literal[
    "connection",
    "timeout",
    "http",
    "url4",
    "protocol",
    "skipped",
]


@dataclass(frozen=True, slots=True)
class EvaluationFailure:
    """One typed case failure returned by the complete engine-side evaluation graph."""

    case_id: str
    kind: FailureKind
    message: str
    status: int | None = None
    code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _nonblank(self.case_id, "failure case ID"))
        if self.kind not in {
            "connection",
            "timeout",
            "http",
            "url4",
            "protocol",
            "skipped",
        }:
            raise ValueError(f"unknown evaluation failure kind {self.kind!r}")
        object.__setattr__(self, "message", _nonblank(self.message, "failure message"))
        if self.status is not None and (
            isinstance(self.status, bool) or not isinstance(self.status, int) or self.status < 100
        ):
            raise ValueError("failure status must be an HTTP status or None")
        if self.code is not None:
            object.__setattr__(self, "code", _nonblank(self.code, "failure code"))

    def _to_wire(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "message": self.message,
            "status": self.status,
            "code": self.code,
        }


@dataclass(frozen=True, slots=True, init=False)
class MemberReport:
    """One Fusion member's summary over the common paired case set."""

    model: str
    score: float | None
    _metric_items: tuple[tuple[str, float], ...] = field(repr=False)

    def __init__(
        self,
        *,
        model: str,
        score: float | None,
        metrics: Mapping[str, float],
    ) -> None:
        object.__setattr__(self, "model", _nonblank(model, "member report model"))
        object.__setattr__(
            self,
            "score",
            None if score is None else _unit_float(score, "member report score"),
        )
        object.__setattr__(self, "_metric_items", _metrics(metrics, "member report"))

    @property
    def metrics(self) -> Mapping[str, float]:
        return MappingProxyType(dict(self._metric_items))

    def _to_wire(self) -> dict[str, object]:
        return {
            "model": self.model,
            "score": self.score,
            "metrics": dict(self._metric_items),
        }


@dataclass(frozen=True, slots=True, init=False)
class Report:
    """One paired Recipe-versus-members benchmark comparison."""

    benchmark_id: str
    recipe_name: str
    url4: str
    n_cases: int
    n_scored: int
    coverage: float
    score: float | None
    baseline: float | None
    gain: float | None
    failures: tuple[EvaluationFailure, ...]
    _member_items: tuple[tuple[str, MemberReport], ...] = field(repr=False)
    _metric_items: tuple[tuple[str, float], ...] = field(repr=False)

    def __init__(
        self,
        *,
        benchmark_id: str,
        recipe_name: str,
        url4: str,
        n_cases: int,
        n_scored: int,
        coverage: float,
        score: float | None,
        baseline: float | None,
        gain: float | None,
        members: Mapping[str, MemberReport] | Sequence[tuple[str, MemberReport]],
        metrics: Mapping[str, float],
        failures: Sequence[EvaluationFailure],
    ) -> None:
        total, scored, normalized_coverage = _counts(n_cases, n_scored, coverage)
        member_items = tuple(members.items()) if isinstance(members, Mapping) else tuple(members)
        _members(member_items)
        normalized_score = None if score is None else _unit_float(score, "report score")
        normalized_baseline = None if baseline is None else _unit_float(baseline, "report baseline")
        normalized_gain = None if gain is None else _gain(gain)
        metric_items = _metrics(metrics, "report")
        normalized_failures = _failures(failures)
        _report_state(
            scored,
            normalized_score,
            normalized_baseline,
            normalized_gain,
            member_items,
            metric_items,
        )

        values = {
            "benchmark_id": _nonblank(benchmark_id, "report benchmark ID"),
            "recipe_name": _nonblank(recipe_name, "report recipe name"),
            "url4": _nonblank(url4, "report URL4"),
            "n_cases": total,
            "n_scored": scored,
            "coverage": normalized_coverage,
            "score": normalized_score,
            "baseline": normalized_baseline,
            "gain": normalized_gain,
            "failures": normalized_failures,
            "_member_items": member_items,
            "_metric_items": metric_items,
        }
        for attribute, value in values.items():
            object.__setattr__(self, attribute, value)

    @property
    def members(self) -> Mapping[str, MemberReport]:
        return MappingProxyType(dict(self._member_items))

    @property
    def metrics(self) -> Mapping[str, float]:
        return MappingProxyType(dict(self._metric_items))

    @property
    def complete(self) -> bool:
        return not self.failures

    def __repr__(self) -> str:
        from screamingface._report_display import report_repr

        return report_repr(self)

    def _repr_html_(self) -> str:
        """Return the rich notebook representation of this report."""

        from screamingface._report_display import report_html

        return report_html(self)

    def to_dict(self) -> dict[str, object]:
        """Return the complete public report as JSON-compatible values."""

        return {
            "benchmark_id": self.benchmark_id,
            "recipe_name": self.recipe_name,
            "url4": self.url4,
            "n_cases": self.n_cases,
            "n_scored": self.n_scored,
            "coverage": self.coverage,
            "score": self.score,
            "baseline": self.baseline,
            "gain": self.gain,
            "members": {member_id: member._to_wire() for member_id, member in self._member_items},
            "metrics": dict(self._metric_items),
            "failures": [failure._to_wire() for failure in self.failures],
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True, init=False)
class CandidateReport:
    """One candidate's aggregate result over a shared benchmark case set."""

    name: str
    n_cases: int
    n_scored: int
    coverage: float
    score: float | None
    failures: tuple[EvaluationFailure, ...]
    _metric_items: tuple[tuple[str, float], ...] = field(repr=False)

    def __init__(
        self,
        *,
        name: str,
        n_cases: int,
        n_scored: int,
        coverage: float,
        score: float | None,
        metrics: Mapping[str, float],
        failures: Sequence[EvaluationFailure],
    ) -> None:
        total, scored, normalized_coverage = _counts(n_cases, n_scored, coverage)
        normalized_score = None if score is None else _unit_float(score, "candidate score")
        metric_items = _metrics(metrics, "candidate report")
        normalized_failures = _failures(failures)
        if scored == 0 and (normalized_score is not None or metric_items):
            raise ValueError("an unscored candidate cannot contain a score or metrics")
        if scored > 0 and normalized_score is None:
            raise ValueError("a scored candidate requires a score")
        object.__setattr__(self, "name", _nonblank(name, "candidate name"))
        object.__setattr__(self, "n_cases", total)
        object.__setattr__(self, "n_scored", scored)
        object.__setattr__(self, "coverage", normalized_coverage)
        object.__setattr__(self, "score", normalized_score)
        object.__setattr__(self, "failures", normalized_failures)
        object.__setattr__(self, "_metric_items", metric_items)

    @property
    def metrics(self) -> Mapping[str, float]:
        return MappingProxyType(dict(self._metric_items))

    @property
    def complete(self) -> bool:
        return not self.failures

    def _to_wire(self) -> dict[str, object]:
        return {
            "n_cases": self.n_cases,
            "n_scored": self.n_scored,
            "coverage": self.coverage,
            "score": self.score,
            "metrics": dict(self._metric_items),
            "failures": [failure._to_wire() for failure in self.failures],
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True, init=False)
class StudyReport:
    """An ordered comparison of independently named candidates over one benchmark slice."""

    benchmark_id: str
    url4: str
    case_ids: tuple[str, ...]
    _candidate_items: tuple[tuple[str, CandidateReport], ...] = field(repr=False)

    def __init__(
        self,
        *,
        benchmark_id: str,
        url4: str,
        case_ids: Sequence[str],
        candidates: Mapping[str, CandidateReport] | Sequence[tuple[str, CandidateReport]],
    ) -> None:
        ids = tuple(_nonblank(value, "study case ID") for value in case_ids)
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("study case IDs must be non-empty and unique")
        items = tuple(candidates.items()) if isinstance(candidates, Mapping) else tuple(candidates)
        if not items:
            raise ValueError("a study report requires at least one candidate")
        names: set[str] = set()
        for name, candidate in items:
            normalized = _nonblank(name, "study candidate name")
            if normalized in names:
                raise ValueError(f"duplicate study candidate {normalized!r}")
            names.add(normalized)
            if not isinstance(candidate, CandidateReport) or candidate.name != normalized:
                raise TypeError("study candidates must match their sf.CandidateReport names")
            if candidate.n_cases != len(ids):
                raise ValueError("study candidates must share the report case set")
        object.__setattr__(self, "benchmark_id", _nonblank(benchmark_id, "study benchmark ID"))
        object.__setattr__(self, "url4", _nonblank(url4, "study URL4"))
        object.__setattr__(self, "case_ids", ids)
        object.__setattr__(self, "_candidate_items", items)

    @property
    def candidates(self) -> Mapping[str, CandidateReport]:
        return MappingProxyType(dict(self._candidate_items))

    @property
    def complete(self) -> bool:
        return all(candidate.complete for _, candidate in self._candidate_items)

    @property
    def best(self) -> CandidateReport | None:
        scored = [
            candidate for _, candidate in self._candidate_items if candidate.score is not None
        ]
        return (
            max(scored, key=lambda value: value.score if value.score is not None else -1.0)
            if scored
            else None
        )

    def __repr__(self) -> str:
        from screamingface._report_display import study_report_repr

        return study_report_repr(self)

    def _repr_html_(self) -> str:
        """Return the rich notebook representation of this candidate study."""

        from screamingface._report_display import study_report_html

        return study_report_html(self)

    def to_dict(self) -> dict[str, object]:
        return {
            "benchmark_id": self.benchmark_id,
            "url4": self.url4,
            "case_ids": list(self.case_ids),
            "candidates": {name: candidate._to_wire() for name, candidate in self._candidate_items},
            "complete": self.complete,
        }


def _report_state(
    n_scored: int,
    score: float | None,
    baseline: float | None,
    gain: float | None,
    members: tuple[tuple[str, MemberReport], ...],
    metrics: tuple[tuple[str, float], ...],
) -> None:
    if n_scored == 0:
        _unscored_state(score, baseline, gain, members, metrics)
        return
    _scored_state(score, baseline, gain, members)


def _unscored_state(
    score: float | None,
    baseline: float | None,
    gain: float | None,
    members: tuple[tuple[str, MemberReport], ...],
    metrics: tuple[tuple[str, float], ...],
) -> None:
    if score is not None or baseline is not None or gain is not None:
        raise ValueError("an unscored report cannot contain headline scores")
    if any(member.score is not None for _, member in members) or metrics:
        raise ValueError("an unscored report cannot contain member scores or metrics")
    if any(member.metrics for _, member in members):
        raise ValueError("an unscored report cannot contain member metrics")


def _scored_state(
    score: float | None,
    baseline: float | None,
    gain: float | None,
    members: tuple[tuple[str, MemberReport], ...],
) -> None:
    member_scores = tuple(member.score for _, member in members)

    if score is None or baseline is None or gain is None:
        raise ValueError("a scored report requires all headline scores")
    if any(member_score is None for member_score in member_scores):
        raise ValueError("a scored report requires every member score")
    numeric_member_scores = tuple(
        member_score for member_score in member_scores if member_score is not None
    )
    expected_baseline = max(numeric_member_scores)
    if not math.isclose(baseline, expected_baseline, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("report baseline must equal the best member score")
    if not math.isclose(gain, score - baseline, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("report gain must equal score - baseline")


def _counts(n_cases: object, n_scored: object, coverage: object) -> tuple[int, int, float]:
    total = _positive_int(n_cases, "report case count")
    scored = _nonnegative_int(n_scored, "report scored count")
    if scored > total:
        raise ValueError("report scored count cannot exceed case count")
    normalized_coverage = _unit_float(coverage, "report coverage")
    if not math.isclose(
        normalized_coverage,
        scored / total,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("report coverage must equal n_scored / n_cases")
    return total, scored, normalized_coverage


def _failures(values: Sequence[EvaluationFailure]) -> tuple[EvaluationFailure, ...]:
    failures = tuple(values)
    if not all(isinstance(failure, EvaluationFailure) for failure in failures):
        raise TypeError("report failures must be sf.EvaluationFailure values")
    return failures


def _members(items: tuple[tuple[str, MemberReport], ...]) -> None:
    if not items:
        raise ValueError("a report requires at least one member")
    expected = tuple(f"member_{position}" for position in range(1, len(items) + 1))
    observed: list[str] = []
    for member_id, member in items:
        observed.append(_nonblank(member_id, "report member slot ID"))
        if not isinstance(member, MemberReport):
            raise TypeError("report members must be sf.MemberReport values")
    if tuple(observed) != expected:
        raise ValueError("report member slots must be contiguous member_1 through member_n")


def _metrics(values: Mapping[str, float], owner: str) -> tuple[tuple[str, float], ...]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{owner} metrics must be a mapping")
    return tuple(
        (
            _nonblank(key, f"{owner} metric name"),
            _unit_float(value, f"{owner} metric {key!r}"),
        )
        for key, value in values.items()
    )


def _unit_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{label} must be finite and between 0 and 1")
    return normalized


def _gain(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("report gain must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not -1.0 <= normalized <= 1.0:
        raise ValueError("report gain must be finite and between -1 and 1")
    return normalized


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be blank")
    return value


__all__ = [
    "CandidateReport",
    "EvaluationFailure",
    "FailureKind",
    "MemberReport",
    "Report",
    "StudyReport",
]
