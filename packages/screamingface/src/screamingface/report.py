"""Immutable public Report values."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

from screamingface._evaluation.model import _canonical_url4
from screamingface._named_values import _NamedValues
from screamingface._operation_projection import _operation_dict, _require_operation_references
from screamingface._report_primitives import (
    Failure,
    Usage,
    _duration,
    _nonblank,
    _usage,
)
from screamingface.case_result import CaseGrade, CaseResult, Check, Evidence, EvidenceProducer
from screamingface.discovery import BenchmarkInfo
from screamingface.operation import OperationInfo, _operation_dag

type RecipeKind = Literal["model", "fusion"]


@dataclass(frozen=True, slots=True, init=False)
class MemberResult:
    """Compact outcome for one direct Fusion member.

    Runtime fields are ``None`` until the Engine attributes spans to this member's stable
    operation ID. An empty Usage or Failure collection means attribution was available and
    observed no activity or failures; it must not stand in for unavailable attribution.
    """

    operation_id: str
    name: str
    kind: RecipeKind
    models: tuple[str, ...]
    failures: tuple[Failure, ...] | None
    duration_ms: int | None
    usage: Usage | None

    def __init__(
        self,
        *,
        operation_id: str,
        name: str,
        kind: RecipeKind,
        models: Sequence[str],
        failures: Sequence[Failure] | None,
        duration_ms: int | None,
        usage: Usage | None,
    ) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _nonblank(operation_id, "Member operation_id"),
        )
        object.__setattr__(self, "name", _nonblank(name, "Member name"))
        object.__setattr__(self, "kind", _kind(kind, "Member"))
        object.__setattr__(self, "models", _models(models, "Member"))
        object.__setattr__(
            self,
            "failures",
            None if failures is None else _failures(failures, "Member"),
        )
        object.__setattr__(self, "duration_ms", _duration(duration_ms, "Member"))
        object.__setattr__(self, "usage", None if usage is None else _usage(usage, "Member"))

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "name": self.name,
            "kind": self.kind,
            "models": list(self.models),
            "failures": (
                None if self.failures is None else [failure.to_dict() for failure in self.failures]
            ),
            "duration_ms": self.duration_ms,
            "usage": None if self.usage is None else self.usage.to_dict(),
        }


@dataclass(frozen=True, slots=True, init=False)
class CandidateResult:
    """One independently executed Candidate outcome; a higher score is always better."""

    run_id: str
    started_at: datetime
    completed_at: datetime
    name: str
    kind: RecipeKind
    url4: str
    models: tuple[str, ...]
    operations: tuple[OperationInfo, ...]
    score: float | None
    cases: tuple[CaseResult, ...]
    members: tuple[MemberResult, ...]
    failures: tuple[Failure, ...]
    usage: Usage
    _metric_items: tuple[tuple[str, float], ...] = field(repr=False)

    def __init__(
        self,
        *,
        run_id: str,
        started_at: datetime,
        completed_at: datetime,
        name: str,
        kind: RecipeKind,
        url4: str,
        models: Sequence[str],
        operations: Sequence[OperationInfo],
        score: float | None,
        metrics: Mapping[str, float],
        cases: Sequence[CaseResult],
        members: Sequence[MemberResult],
        failures: Sequence[Failure],
        usage: Usage,
    ) -> None:
        selected_score = _optional_number(score, "Candidate score")
        metric_items = _metrics(metrics)
        if selected_score is None and metric_items:
            raise ValueError("a failed or unscored Candidate cannot contain metrics")
        selected_kind, selected_models, selected_members, selected_failures = _candidate_shape(
            kind,
            models,
            members,
            failures,
            scored=selected_score is not None,
        )
        selected_operations = _operation_dag(operations)
        selected_cases = _case_results(cases)
        _require_operation_references(
            selected_operations,
            selected_members,
            selected_failures,
        )
        start, end = _time_range(
            started_at,
            completed_at,
            label="Candidate",
        )
        values = {
            "run_id": _nonblank(run_id, "Candidate run_id"),
            "started_at": start,
            "completed_at": end,
            "name": _nonblank(name, "Candidate name"),
            "kind": selected_kind,
            "url4": _canonical_url4(url4, "Candidate"),
            "models": selected_models,
            "operations": selected_operations,
            "score": selected_score,
            "cases": selected_cases,
            "members": selected_members,
            "failures": selected_failures,
            "usage": _usage(usage, "Candidate"),
            "_metric_items": metric_items,
        }
        for attribute, value in values.items():
            object.__setattr__(self, attribute, value)

    @property
    def metrics(self) -> Mapping[str, float]:
        return MappingProxyType(dict(self._metric_items))

    @property
    def duration_ms(self) -> int:
        return round((self.completed_at - self.started_at).total_seconds() * 1000)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "started_at": _timestamp_text(self.started_at),
            "completed_at": _timestamp_text(self.completed_at),
            "name": self.name,
            "kind": self.kind,
            "url4": self.url4,
            "models": list(self.models),
            "operations": [_operation_dict(operation) for operation in self.operations],
            "score": self.score,
            "metrics": dict(self._metric_items),
            "cases": [case.to_dict() for case in self.cases],
            "members": [member.to_dict() for member in self.members],
            "failures": [failure.to_dict() for failure in self.failures],
            "duration_ms": self.duration_ms,
            "usage": self.usage.to_dict(),
        }


class _CandidateResults(_NamedValues[CandidateResult]):
    """Private collection behind Report.candidates."""

    def __init__(self, values: Sequence[CandidateResult]) -> None:
        super().__init__(
            values,
            empty_message="a Report requires at least one Candidate",
            item_type=CandidateResult,
            type_message="Report candidates must be sf.CandidateResult values",
            duplicate_label="Candidate",
        )


@dataclass(frozen=True, slots=True, init=False)
class Report:
    """One ordered collection of independently executed Candidate Results."""

    benchmark: BenchmarkInfo
    case_count: int
    candidates: _CandidateResults

    def __init__(
        self,
        *,
        benchmark: BenchmarkInfo,
        case_count: int,
        candidates: Sequence[CandidateResult],
    ) -> None:
        if not isinstance(benchmark, BenchmarkInfo):
            raise TypeError("Report benchmark must be an sf.BenchmarkInfo")
        benchmark._result_dict(case_count)
        selected_candidates = _CandidateResults(candidates)
        for candidate in selected_candidates:
            if len(candidate.cases) != case_count:
                raise ValueError(
                    "every Candidate Result must contain the Report's selected Case count"
                )
        values = {
            "benchmark": benchmark,
            "case_count": case_count,
            "candidates": selected_candidates,
        }
        for attribute, value in values.items():
            object.__setattr__(self, attribute, value)

    @property
    def started_at(self) -> datetime:
        return min(candidate.started_at for candidate in self.candidates)

    @property
    def completed_at(self) -> datetime:
        return max(candidate.completed_at for candidate in self.candidates)

    @property
    def duration_ms(self) -> int:
        return round((self.completed_at - self.started_at).total_seconds() * 1000)

    @property
    def usage(self) -> Usage:
        return _combined_usage(tuple(candidate.usage for candidate in self.candidates))

    @property
    def failures(self) -> tuple[Failure, ...]:
        flattened: list[Failure] = []
        for candidate in self.candidates:
            flattened.extend(candidate.failures)
            for member in candidate.members:
                if member.failures is not None:
                    flattened.extend(member.failures)
            for case in candidate.cases:
                flattened.extend(case.failures)
        return tuple(flattened)

    @property
    def ok(self) -> bool:
        return not self.failures and all(
            candidate.score is not None for candidate in self.candidates
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "screamingface.report.v1",
            "started_at": _timestamp_text(self.started_at),
            "completed_at": _timestamp_text(self.completed_at),
            "benchmark": self.benchmark._result_dict(self.case_count),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "usage": self.usage.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def __repr__(self) -> str:
        candidates = ", ".join(repr(candidate.name) for candidate in self.candidates)
        return f"Report(benchmark={self.benchmark.id!r}, candidates=[{candidates}], ok={self.ok})"


def _kind(value: object, label: str) -> RecipeKind:
    if value == "model":
        return "model"
    if value == "fusion":
        return "fusion"
    raise ValueError(f"{label} kind must be 'model' or 'fusion'")


def _models(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, str | bytes) or not isinstance(values, Sequence):
        raise TypeError(f"{label} models must be an ordered sequence")
    selected = tuple(_nonblank(value, f"{label} model route") for value in values)
    if not selected:
        raise ValueError(f"{label} models must not be empty")
    if len(selected) != len(set(selected)):
        raise ValueError(f"{label} models must be unique")
    return selected


def _failures(values: Sequence[Failure], label: str) -> tuple[Failure, ...]:
    selected = tuple(values)
    if any(not isinstance(value, Failure) for value in selected):
        raise TypeError(f"{label} failures must be sf.Failure values")
    return selected


def _members(values: Sequence[MemberResult]) -> tuple[MemberResult, ...]:
    selected = tuple(values)
    if any(not isinstance(value, MemberResult) for value in selected):
        raise TypeError("Candidate members must be sf.MemberResult values")
    names = [value.name for value in selected]
    if len(names) != len(set(names)):
        raise ValueError("Candidate member names must be unique")
    operation_ids = [value.operation_id for value in selected]
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("Candidate member operation IDs must be unique")
    return selected


def _case_results(values: Sequence[CaseResult]) -> tuple[CaseResult, ...]:
    if isinstance(values, str | bytes) or not isinstance(values, Sequence):
        raise TypeError("Candidate cases must be an ordered sequence")
    selected = tuple(values)
    if any(not isinstance(value, CaseResult) for value in selected):
        raise TypeError("Candidate cases must contain sf.CaseResult values")
    if not selected:
        raise ValueError("a Candidate Result requires at least one Case Result")
    ids = [value.case_id for value in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("Candidate Case Result ids must be unique")
    return selected


def _candidate_shape(
    kind: object,
    models: Sequence[str],
    members: Sequence[MemberResult],
    failures: Sequence[Failure],
    *,
    scored: bool,
) -> tuple[
    RecipeKind,
    tuple[str, ...],
    tuple[MemberResult, ...],
    tuple[Failure, ...],
]:
    selected_kind = _kind(kind, "Candidate")
    selected_models = _models(models, "Candidate")
    selected_members = _members(members)
    selected_failures = _failures(failures, "Candidate")
    if selected_kind == "model":
        if len(selected_models) != 1:
            raise ValueError("a Model Candidate must contain exactly one model route")
        if selected_members:
            raise ValueError("a Model Candidate cannot contain members")
    elif len(selected_members) < 2:
        raise ValueError("a Fusion Candidate requires at least two direct members")
    if scored and selected_failures:
        raise ValueError("a failed Candidate cannot contain a score or metrics")
    return selected_kind, selected_models, selected_members, selected_failures


def _time_range(start: object, end: object, *, label: str) -> tuple[datetime, datetime]:
    selected_start = _timestamp(start, f"{label} started_at")
    selected_end = _timestamp(end, f"{label} completed_at")
    if selected_end < selected_start:
        raise ValueError(f"{label} completed_at cannot precede started_at")
    return selected_start, selected_end


def _combined_usage(values: tuple[Usage, ...]) -> Usage:
    """Sum fields only when every Candidate Run reported that field."""

    def total(name: str) -> int | None:
        observed = tuple(getattr(value, name) for value in values)
        if any(value is None for value in observed):
            return None
        return sum(value for value in observed if value is not None)

    costs = tuple(value.cost_usd for value in values)
    cost = (
        None
        if any(value is None for value in costs)
        else sum((value for value in costs if value is not None), Decimal())
    )
    return Usage(
        input_tokens=total("input_tokens"),
        output_tokens=total("output_tokens"),
        cache_read_tokens=total("cache_read_tokens"),
        cache_creation_tokens=total("cache_creation_tokens"),
        reasoning_tokens=total("reasoning_tokens"),
        cost_usd=cost,
    )


def _optional_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{label} must be a finite number or None")
    selected = float(value)
    if not math.isfinite(selected):
        raise ValueError(f"{label} must be a finite number or None")
    return selected


def _metrics(values: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    if not isinstance(values, Mapping):
        raise TypeError("Candidate metrics must be a mapping")
    selected: list[tuple[str, float]] = []
    for name, value in values.items():
        normalized = _optional_number(value, f"Candidate metric {name!r}")
        if normalized is None:
            raise TypeError(f"Candidate metric {name!r} must be a finite number")
        selected.append((_nonblank(name, "Candidate metric name"), normalized))
    return tuple(selected)


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")
    return value


def _timestamp_text(value: datetime) -> str:
    text = value.isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


__all__ = [
    "CaseGrade",
    "CaseResult",
    "CandidateResult",
    "Check",
    "Evidence",
    "EvidenceProducer",
    "Failure",
    "MemberResult",
    "OperationInfo",
    "Report",
    "Usage",
]
