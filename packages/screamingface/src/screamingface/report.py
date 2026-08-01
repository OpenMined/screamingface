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

from screamingface._evaluation.model import Operation, _canonical_url4, _operation_dag
from screamingface._named_values import _NamedValues
from screamingface._operation_projection import _operation_dict, _require_operation_references
from screamingface._report_primitives import (
    Failure,
    Usage,
    _duration,
    _nonblank,
    _usage,
)
from screamingface.discovery import BenchmarkInfo

type RecipeKind = Literal["model", "fusion"]


@dataclass(frozen=True, slots=True, init=False)
class MemberResult:
    """Compact outcome for one direct Fusion member."""

    operation_id: str
    name: str
    kind: RecipeKind
    models: tuple[str, ...]
    failures: tuple[Failure, ...]
    duration_ms: int | None
    usage: Usage

    def __init__(
        self,
        *,
        operation_id: str,
        name: str,
        kind: RecipeKind,
        models: Sequence[str],
        failures: Sequence[Failure],
        duration_ms: int | None,
        usage: Usage,
    ) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _nonblank(operation_id, "Member operation_id"),
        )
        object.__setattr__(self, "name", _nonblank(name, "Member name"))
        object.__setattr__(self, "kind", _kind(kind, "Member"))
        object.__setattr__(self, "models", _models(models, "Member"))
        object.__setattr__(self, "failures", _failures(failures, "Member"))
        object.__setattr__(self, "duration_ms", _duration(duration_ms, "Member"))
        object.__setattr__(self, "usage", _usage(usage, "Member"))

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "name": self.name,
            "kind": self.kind,
            "models": list(self.models),
            "failures": [failure.to_dict() for failure in self.failures],
            "duration_ms": self.duration_ms,
            "usage": self.usage.to_dict(),
        }


@dataclass(frozen=True, slots=True, init=False)
class CandidateResult:
    """One independently executed and scored Candidate outcome."""

    run_id: str
    started_at: datetime
    completed_at: datetime
    name: str
    kind: RecipeKind
    url4: str
    models: tuple[str, ...]
    operations: tuple[Operation, ...]
    score: float | None
    members: tuple[MemberResult, ...]
    failures: tuple[Failure, ...]
    usage: Usage
    baseline: float | None
    gain: float | None
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
        operations: Sequence[Operation],
        score: float | None,
        metrics: Mapping[str, float],
        members: Sequence[MemberResult],
        failures: Sequence[Failure],
        usage: Usage,
        baseline: float | None = None,
        gain: float | None = None,
    ) -> None:
        normalized_score = _optional_number(score, "Candidate score")
        metric_items = _metrics(metrics)
        if normalized_score is None and metric_items:
            raise ValueError("a failed or unscored Candidate cannot contain metrics")
        selected_kind, selected_models, selected_members, selected_failures = _candidate_shape(
            kind,
            models,
            members,
            failures,
            scored=normalized_score is not None,
        )
        selected_operations = _operation_dag(operations)
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
            "score": normalized_score,
            "members": selected_members,
            "failures": selected_failures,
            "usage": _usage(usage, "Candidate"),
            "baseline": _optional_number(baseline, "Candidate baseline"),
            "gain": _optional_number(gain, "Candidate gain"),
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
        value: dict[str, object] = {
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
            "members": [member.to_dict() for member in self.members],
            "failures": [failure.to_dict() for failure in self.failures],
            "duration_ms": self.duration_ms,
            "usage": self.usage.to_dict(),
        }
        if self.baseline is not None:
            value["baseline"] = self.baseline
        if self.gain is not None:
            value["gain"] = self.gain
        return value


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
        _validate_primary_scores(selected_candidates, benchmark)
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
                flattened.extend(member.failures)
        return tuple(flattened)

    @property
    def ok(self) -> bool:
        return not self.failures

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


def _validate_primary_scores(
    candidates: _CandidateResults,
    benchmark: BenchmarkInfo,
) -> None:
    for candidate in candidates:
        primary = candidate.metrics.get(benchmark.primary_metric)
        if candidate.score is None:
            if primary is not None:
                raise ValueError("unscored Candidate cannot contain its primary metric")
            continue
        if primary is None or not math.isclose(
            candidate.score,
            primary,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("Candidate score must equal the Benchmark primary metric")
        if (candidate.baseline is None) != (candidate.gain is None):
            raise ValueError("Candidate baseline and gain must be present together")
        if candidate.baseline is not None and candidate.gain is not None:
            expected = (
                candidate.score - candidate.baseline
                if benchmark.score_direction == "maximize"
                else candidate.baseline - candidate.score
            )
            if not math.isclose(candidate.gain, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("Candidate gain must be direction-aware")


__all__ = [
    "CandidateResult",
    "Failure",
    "MemberResult",
    "Report",
    "Usage",
]
