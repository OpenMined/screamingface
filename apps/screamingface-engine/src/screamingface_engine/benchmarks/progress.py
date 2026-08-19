"""Run-scoped, Benchmark-owned provisional progress over the existing URL4 lifecycle."""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from screamingface_engine.benchmarks.contract import CandidateResult, CaseId, validate_case_id
from screamingface_engine.benchmarks.evaluation import (
    AggregateAdapter,
    benchmark_unavailable,
    compact_json,
    json_object,
    positive_count,
)
from url4.peer.server import Request, Url4Node

type CaseStage = Literal["candidate", "grading", "complete"]
type ProgressSink = Callable[["BenchmarkProgressSignal"], None]
type CaseOrder = Callable[[], Sequence[CaseId]]

PROGRESS_LOG_KIND = "screamingface.benchmark.progress"
_logger = logging.getLogger(__name__)
_PENDING_ROW = {
    "error": {
        "kind": "pending_case",
        "message": "the Case has not completed",
    }
}


class _ProgressComputationError(RuntimeError):
    """A non-authoritative snapshot failed before it reached the transport sink."""


@dataclass(frozen=True, slots=True)
class BenchmarkProgressSignal:
    """One complete aggregate snapshot; safe to expose without Case material."""

    benchmark_id: str
    benchmark_revision: str
    total: int
    queued: int
    running_candidate: int
    grading: int
    complete: int
    scored: int
    coverage: float
    provisional_score: float | None

    def __post_init__(self) -> None:
        _validate_signal(self)

    def attributes(self) -> dict[str, str | int | float | bool | None]:
        """Scalar semantic attributes carried by the existing structured-log wire."""

        return {
            "screamingface.event.kind": PROGRESS_LOG_KIND,
            "benchmark.id": self.benchmark_id,
            "benchmark.revision": self.benchmark_revision,
            "cases.total": self.total,
            "cases.queued": self.queued,
            "cases.running_candidate": self.running_candidate,
            "cases.grading": self.grading,
            "cases.complete": self.complete,
            "cases.scored": self.scored,
            "score.coverage": self.coverage,
            "score.provisional": self.provisional_score,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkProgressAdapter:
    """One Benchmark's immutable selection and existing aggregate implementation."""

    benchmark_id: str
    benchmark_revision: str
    available_case_count: int
    case_order: CaseOrder
    aggregate: AggregateAdapter

    def __post_init__(self) -> None:
        for name in ("benchmark_id", "benchmark_revision"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"BenchmarkProgressAdapter {name} must be non-empty text")
        positive_count(self.available_case_count, "available_case_count")
        if not callable(self.case_order) or not callable(self.aggregate):
            raise TypeError("BenchmarkProgressAdapter callables must be callable")

    @property
    def key(self) -> tuple[str, str]:
        return self.benchmark_id, self.benchmark_revision

    def selected_case_ids(self, count: int) -> tuple[CaseId, ...]:
        positive_count(count, "selected_case_count")
        if count > self.available_case_count:
            raise ValueError("selected_case_count cannot exceed available_case_count")
        values = tuple(self.case_order())
        if len(values) < count:
            raise ValueError("Benchmark progress Case order is shorter than the selection")
        selected = tuple(validate_case_id(value) for value in values[:count])
        if any(value is None for value in selected):  # pragma: no cover - validator raises
            raise AssertionError("validated Case ids cannot be null")
        typed = tuple(value for value in selected if value is not None)
        if len(set(typed)) != len(typed):
            raise ValueError("Benchmark progress Case order contains duplicate ids")
        return typed


@dataclass(slots=True)
class _RunProgress:
    adapter: BenchmarkProgressAdapter
    selected_case_ids: tuple[CaseId, ...]
    stages: dict[CaseId, CaseStage] = field(default_factory=dict)
    rows: dict[CaseId, object] = field(default_factory=dict)
    last_signal: BenchmarkProgressSignal | None = None


@dataclass(slots=True)
class _ProgressSession:
    sink: ProgressSink
    runs: dict[tuple[str, str], _RunProgress] = field(default_factory=dict)

    def observe(
        self,
        adapter: BenchmarkProgressAdapter,
        *,
        selected_case_count: int,
        case_id: CaseId,
        stage: CaseStage,
        row: object | None,
    ) -> None:
        try:
            progress = self._progress(adapter, selected_case_count)
            selected_case_id = _selected_case_id(case_id, progress.selected_case_ids)
            current = progress.stages.get(selected_case_id)
            if current == "complete":
                return
            if stage == "grading" and current not in {"candidate", "grading"}:
                raise ValueError("a Case cannot enter grading before Candidate execution")
            if stage == "complete":
                if row is None:
                    raise ValueError("a completed Case must carry its evaluation row")
                progress.rows[selected_case_id] = row
            progress.stages[selected_case_id] = stage
            signal = _snapshot(progress)
        except Exception as exc:
            raise _ProgressComputationError("could not compute Benchmark progress") from exc
        self._publish(progress, signal)

    def finish(
        self,
        adapter: BenchmarkProgressAdapter,
        *,
        selected_case_count: int,
        result: Mapping[str, Any],
    ) -> None:
        try:
            progress = self._progress(adapter, selected_case_count)
            candidate = CandidateResult.model_validate(result)
            if (
                candidate.benchmark_id != adapter.benchmark_id
                or candidate.benchmark_revision != adapter.benchmark_revision
                or candidate.case_count != selected_case_count
            ):
                raise ValueError(
                    "final Candidate Result does not match Benchmark progress identity"
                )
            progress.stages = {case_id: "complete" for case_id in progress.selected_case_ids}
            signal = _signal_from_result(progress, candidate)
        except Exception as exc:
            raise _ProgressComputationError("could not reconcile Benchmark progress") from exc
        self._publish(progress, signal)

    def _publish(
        self,
        progress: _RunProgress,
        signal: BenchmarkProgressSignal,
    ) -> None:
        if signal == progress.last_signal:
            return
        self.sink(signal)
        progress.last_signal = signal

    def _progress(
        self,
        adapter: BenchmarkProgressAdapter,
        selected_case_count: int,
    ) -> _RunProgress:
        selected = adapter.selected_case_ids(selected_case_count)
        existing = self.runs.get(adapter.key)
        if existing is None:
            existing = _RunProgress(adapter=adapter, selected_case_ids=selected)
            self.runs[adapter.key] = existing
        elif existing.selected_case_ids != selected:
            raise ValueError("Benchmark progress selection changed within one Run")
        return existing


_SESSION: ContextVar[_ProgressSession | None] = ContextVar(
    "screamingface_benchmark_progress_session",
    default=None,
)


@contextmanager
def benchmark_progress_session(sink: ProgressSink) -> Iterator[None]:
    """Bind one isolated progress fold to this URL4 Run and its child tasks."""

    if not callable(sink):
        raise TypeError("Benchmark progress sink must be callable")
    token = _SESSION.set(_ProgressSession(sink))
    try:
        yield
    finally:
        _SESSION.reset(token)


def progress_endpoint(adapter: BenchmarkProgressAdapter) -> Callable[[Request], str]:
    """Return one pass-through URL4 route that records a Case stage transition."""

    def endpoint(request: Request) -> str:
        try:
            payload = json_object(request.context, "Benchmark progress")
            value = payload["value"]
            if not isinstance(value, str):
                raise ValueError("Benchmark progress value must be text")
        except (KeyError, TypeError, ValueError) as exc:
            raise benchmark_unavailable(str(exc)) from exc
        try:
            if set(payload) != {"case_id", "value"}:
                raise ValueError("Benchmark progress context must carry case_id and value")
            stage, selected_case_count = _progress_intent(request.intent)
            case_id = validate_case_id(payload["case_id"])
            assert case_id is not None
            session = _SESSION.get()
            if session is not None:
                session.observe(
                    adapter,
                    selected_case_count=selected_case_count,
                    case_id=case_id,
                    stage=stage,
                    row=_decode_row(value) if stage == "complete" else None,
                )
        except (KeyError, TypeError, ValueError, _ProgressComputationError):
            _logger.warning("Benchmark progress snapshot skipped", exc_info=True)
        return value

    return endpoint


def final_aggregate(adapter: BenchmarkProgressAdapter) -> AggregateAdapter:
    """Decorate the authoritative aggregate with one final, reconciling snapshot."""

    def aggregate(rows: str, selected_case_count: int) -> dict[str, Any]:
        result = adapter.aggregate(rows, selected_case_count)
        session = _SESSION.get()
        if session is not None:
            try:
                session.finish(
                    adapter,
                    selected_case_count=selected_case_count,
                    result=result,
                )
            except _ProgressComputationError:
                _logger.warning(
                    "Final Benchmark progress snapshot skipped",
                    exc_info=True,
                )
        return result

    return aggregate


def install_progress(
    node: Url4Node,
    *,
    route: str,
    adapter: BenchmarkProgressAdapter,
) -> AggregateAdapter:
    """Install one Benchmark's progress route and return its reconciled aggregate."""

    if not isinstance(node, Url4Node):
        raise TypeError("Benchmark progress node must be a Url4Node")
    if not isinstance(route, str) or not route.startswith("/"):
        raise ValueError("Benchmark progress route must be an absolute URL4 path")
    if route not in frozenset(node.processor_routes()):
        node.endpoint(route)(progress_endpoint(adapter))
    return final_aggregate(adapter)


def _snapshot(progress: _RunProgress) -> BenchmarkProgressSignal:
    result = _provisional_result(progress)
    return _signal_from_result(progress, result)


def _provisional_result(progress: _RunProgress) -> CandidateResult:
    rows = [progress.rows.get(case_id, _PENDING_ROW) for case_id in progress.selected_case_ids]
    payload = progress.adapter.aggregate(compact_json(rows), len(progress.selected_case_ids))
    return CandidateResult.model_validate(payload)


def _signal_from_result(
    progress: _RunProgress,
    result: CandidateResult,
) -> BenchmarkProgressSignal:
    counts = {stage: 0 for stage in ("candidate", "grading", "complete")}
    for stage in progress.stages.values():
        counts[stage] += 1
    total = len(progress.selected_case_ids)
    queued = total - sum(counts.values())
    scored = sum(case.grade is not None and case.grade.score is not None for case in result.cases)
    return BenchmarkProgressSignal(
        benchmark_id=progress.adapter.benchmark_id,
        benchmark_revision=progress.adapter.benchmark_revision,
        total=total,
        queued=queued,
        running_candidate=counts["candidate"],
        grading=counts["grading"],
        complete=counts["complete"],
        scored=scored,
        coverage=round(scored / total, 4),
        provisional_score=result.score,
    )


def _progress_intent(value: str) -> tuple[CaseStage, int]:
    raw_stage, separator, raw_count = value.partition(":")
    if not separator or raw_stage not in {"candidate", "grading", "complete"}:
        raise ValueError("Benchmark progress intent must name candidate, grading, or complete")
    try:
        selected_case_count = int(raw_count)
        positive_count(selected_case_count, "selected_case_count")
    except ValueError as exc:
        raise ValueError(str(exc)) from None
    return cast(CaseStage, raw_stage), selected_case_count


def _selected_case_id(value: CaseId, selected: Sequence[CaseId]) -> CaseId:
    if value in selected:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) in selected:
        return int(value)
    if isinstance(value, int) and str(value) in selected:
        return str(value)
    raise ValueError(f"Benchmark progress references unselected Case {value!r}")


def _decode_row(value: str) -> object:
    try:
        return json.loads(value)
    except ValueError as exc:
        raise ValueError(f"completed Case progress value must be JSON: {exc}") from None


def _validate_signal(value: BenchmarkProgressSignal) -> None:
    for name in ("benchmark_id", "benchmark_revision"):
        text_value = getattr(value, name)
        if not isinstance(text_value, str) or not text_value.strip():
            raise ValueError(f"BenchmarkProgressSignal {name} must be non-empty text")
    _validate_signal_counts(value)
    _validate_signal_score(value)


def _validate_signal_counts(value: BenchmarkProgressSignal) -> None:
    counts = tuple(
        getattr(value, name)
        for name in ("total", "queued", "running_candidate", "grading", "complete", "scored")
    )
    if any(isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in counts):
        raise ValueError("BenchmarkProgressSignal counts must be non-negative integers")
    if value.total < 1:
        raise ValueError("BenchmarkProgressSignal total must be positive")
    if value.queued + value.running_candidate + value.grading + value.complete != value.total:
        raise ValueError("BenchmarkProgressSignal stage counts must sum to total")
    if value.scored > value.complete:
        raise ValueError("BenchmarkProgressSignal scored cannot exceed complete")
    if value.coverage != round(value.scored / value.total, 4):
        raise ValueError("BenchmarkProgressSignal coverage must equal scored / total")


def _validate_signal_score(value: BenchmarkProgressSignal) -> None:
    score = value.provisional_score
    if score is not None and (
        isinstance(score, bool)
        or not isinstance(score, int | float)
        or not math.isfinite(float(score))
    ):
        raise ValueError("BenchmarkProgressSignal score must be finite or null")
    if (value.scored == 0) != (score is None):
        raise ValueError("BenchmarkProgressSignal score presence must match scored Cases")


__all__ = [
    "PROGRESS_LOG_KIND",
    "BenchmarkProgressAdapter",
    "BenchmarkProgressSignal",
    "benchmark_progress_session",
    "final_aggregate",
    "install_progress",
    "progress_endpoint",
]
