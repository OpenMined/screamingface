"""Typed public views over the SF Engine CloudEvents lifecycle."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import ClassVar, Literal

from screamingface.report import Usage as AccountingUsage

type Severity = Literal["DEBUG", "INFO", "WARN", "ERROR"]
type SpanKind = Literal["client", "internal", "server"]
type SpanStatus = Literal["ok", "error"]
type UsageScope = Literal["self", "subtree"]
type TerminationStatus = Literal["succeeded", "failed", "stopped", "timed_out"]


@dataclass(frozen=True, slots=True)
class Event:
    """Common immutable lifecycle Event delivered to callbacks."""

    id: str
    run_id: str
    sequence: int
    timestamp: datetime
    source: str
    traceparent: str | None = None
    tracestate: str | None = None
    kind: ClassVar[str] = "event"

    def __post_init__(self) -> None:
        for name in ("id", "run_id", "source"):
            object.__setattr__(self, name, _nonblank(getattr(self, name), f"Event {name}"))
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise ValueError("Event sequence must be a positive integer")
        if not isinstance(self.timestamp, datetime) or self.timestamp.tzinfo is None:
            raise ValueError("Event timestamp must be timezone-aware")
        for name in ("traceparent", "tracestate"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _nonblank(value, f"Event {name}"))


@dataclass(frozen=True, slots=True)
class Started(Event):
    """A URL4 operation began executing."""

    url4: str = ""
    kind: ClassVar[str] = "started"

    def __post_init__(self) -> None:
        super(Started, self).__post_init__()
        object.__setattr__(self, "url4", _nonblank(self.url4, "Started URL4"))


@dataclass(frozen=True, slots=True, init=False)
class Log(Event):
    """One OpenTelemetry-compatible log record."""

    severity_number: int
    severity_text: Severity
    body: str
    _attributes: Mapping[str, str | int | float | bool | None] = field(repr=False)
    kind: ClassVar[str] = "log"

    def __init__(
        self,
        *,
        id: str,
        run_id: str,
        sequence: int,
        timestamp: datetime,
        source: str,
        severity_number: int,
        severity_text: Severity,
        body: str,
        attributes: Mapping[str, str | int | float | bool | None] = MappingProxyType({}),
        traceparent: str | None = None,
        tracestate: str | None = None,
    ) -> None:
        Event.__init__(
            self,
            id=id,
            run_id=run_id,
            sequence=sequence,
            timestamp=timestamp,
            source=source,
            traceparent=traceparent,
            tracestate=tracestate,
        )
        if isinstance(severity_number, bool) or not isinstance(severity_number, int):
            raise TypeError("Log severity_number must be an integer")
        if severity_text not in {"DEBUG", "INFO", "WARN", "ERROR"}:
            raise ValueError("Log severity_text is invalid")
        if not isinstance(body, str):
            raise TypeError("Log body must be a string")
        object.__setattr__(self, "severity_number", severity_number)
        object.__setattr__(self, "severity_text", severity_text)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "_attributes", _log_attributes(attributes))

    @property
    def attributes(self) -> Mapping[str, str | int | float | bool | None]:
        return self._attributes


@dataclass(frozen=True, slots=True)
class BenchmarkProgress(Event):
    """One Engine-authored, benchmark-native progress snapshot for a Candidate Run."""

    benchmark_id: str = ""
    benchmark_revision: str = ""
    total_cases: int = 0
    queued_cases: int = 0
    running_candidate_cases: int = 0
    grading_cases: int = 0
    complete_cases: int = 0
    scored_cases: int = 0
    coverage: float = 0.0
    provisional_score: float | None = None
    kind: ClassVar[str] = "benchmark_progress"

    def __post_init__(self) -> None:
        super(BenchmarkProgress, self).__post_init__()
        _validate_benchmark_progress(self)


@dataclass(frozen=True, slots=True)
class Span(Event):
    """One OpenTelemetry span with portable GenAI attributes."""

    name: str = ""
    operation: str = ""
    start: datetime | None = None
    end: datetime | None = None
    status: SpanStatus = "ok"
    span_kind: SpanKind = "internal"
    provider: str | None = None
    request_model: str | None = None
    response_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reasons: tuple[str, ...] = ()
    refusal: str | None = None
    kind: ClassVar[str] = "span"

    def __post_init__(self) -> None:
        super(Span, self).__post_init__()
        object.__setattr__(self, "name", _nonblank(self.name, "Span name"))
        object.__setattr__(self, "operation", _nonblank(self.operation, "Span operation"))
        _validate_span_times(self.start, self.end)
        _validate_span_classification(self.status, self.span_kind)
        for name in ("provider", "request_model", "response_model", "refusal"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    _nonblank(value, f"Span {name}"),
                )
        for name in ("input_tokens", "output_tokens"):
            _optional_count(getattr(self, name), f"Span {name}")
        if not isinstance(self.finish_reasons, tuple):
            raise TypeError("Span finish_reasons must be a tuple")
        object.__setattr__(
            self,
            "finish_reasons",
            tuple(_nonblank(reason, "Span finish reason") for reason in self.finish_reasons),
        )


@dataclass(frozen=True, slots=True)
class Usage(Event):
    """One `ai.url4.cost.usage` taxonomy Event."""

    scope: UsageScope = "self"
    provider: str = ""
    model: str = ""
    pricing_version: str = ""
    usage: AccountingUsage = field(default_factory=AccountingUsage)
    kind: ClassVar[str] = "usage"

    def __post_init__(self) -> None:
        super(Usage, self).__post_init__()
        if self.scope not in {"self", "subtree"}:
            raise ValueError("Usage Event scope must be 'self' or 'subtree'")
        for name in ("provider", "model", "pricing_version"):
            object.__setattr__(
                self,
                name,
                _nonblank(getattr(self, name), f"Usage Event {name}"),
            )
        if not isinstance(self.usage, AccountingUsage):
            raise TypeError("Usage Event usage must be an sf.Usage value")


@dataclass(frozen=True, slots=True)
class TerminationError:
    """Structured URL4 failure carried by a terminal Event."""

    code: str
    message: str
    permanent: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _nonblank(self.code, "Termination error code"))
        object.__setattr__(self, "message", _nonblank(self.message, "Termination error message"))
        if not isinstance(self.permanent, bool):
            raise TypeError("Termination error permanent must be a boolean")


@dataclass(frozen=True, slots=True)
class Terminated(Event):
    """The Run reached its terminal state."""

    status: TerminationStatus = "succeeded"
    error: TerminationError | None = None
    kind: ClassVar[str] = "terminated"

    def __post_init__(self) -> None:
        super(Terminated, self).__post_init__()
        if self.status not in {"succeeded", "failed", "stopped", "timed_out"}:
            raise ValueError("Terminated status is invalid")
        if self.error is not None and not isinstance(self.error, TerminationError):
            raise TypeError("Terminated error must be an sf.events.TerminationError")
        if self.status == "succeeded" and self.error is not None:
            raise ValueError("a succeeded termination cannot contain an error")


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _optional_count(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be a non-negative integer")
    if value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _validate_benchmark_progress(value: BenchmarkProgress) -> None:
    for name in ("benchmark_id", "benchmark_revision"):
        object.__setattr__(value, name, _nonblank(getattr(value, name), name))
    _validate_progress_counts(value)
    _validate_progress_score(value)


def _validate_progress_counts(value: BenchmarkProgress) -> None:
    counts = (
        value.total_cases,
        value.queued_cases,
        value.running_candidate_cases,
        value.grading_cases,
        value.complete_cases,
        value.scored_cases,
    )
    if any(isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in counts):
        raise ValueError("BenchmarkProgress counts must be non-negative integers")
    if value.total_cases < 1:
        raise ValueError("BenchmarkProgress total_cases must be positive")
    stage_total = (
        value.queued_cases
        + value.running_candidate_cases
        + value.grading_cases
        + value.complete_cases
    )
    if stage_total != value.total_cases:
        raise ValueError("BenchmarkProgress stage counts must sum to total_cases")
    if value.scored_cases > value.complete_cases:
        raise ValueError("BenchmarkProgress scored_cases cannot exceed complete_cases")
    if (
        isinstance(value.coverage, bool)
        or not isinstance(value.coverage, int | float)
        or not math.isfinite(float(value.coverage))
        or value.coverage != round(value.scored_cases / value.total_cases, 4)
    ):
        raise ValueError("BenchmarkProgress coverage must equal scored_cases / total_cases")


def _validate_progress_score(value: BenchmarkProgress) -> None:
    score = value.provisional_score
    if score is not None and (
        isinstance(score, bool)
        or not isinstance(score, int | float)
        or not math.isfinite(float(score))
    ):
        raise ValueError("BenchmarkProgress provisional_score must be finite or None")
    if (value.scored_cases == 0) != (score is None):
        raise ValueError("BenchmarkProgress provisional_score presence must match scored_cases")


def _validate_span_times(start: datetime | None, end: datetime | None) -> None:
    if start is None or start.tzinfo is None:
        raise ValueError("Span start must be timezone-aware")
    if end is not None and end.tzinfo is None:
        raise ValueError("Span end must be timezone-aware")
    if end is not None and end < start:
        raise ValueError("Span end cannot precede start")


def _validate_span_classification(status: object, span_kind: object) -> None:
    if status not in {"ok", "error"}:
        raise ValueError("Span status must be 'ok' or 'error'")
    if span_kind not in {"client", "internal", "server"}:
        raise ValueError("Span span_kind is invalid")


def _log_attributes(
    values: object,
) -> Mapping[str, str | int | float | bool | None]:
    if not isinstance(values, Mapping):
        raise TypeError("Log attributes must be a mapping")
    selected: dict[str, str | int | float | bool | None] = {}
    for name, value in values.items():
        key = _nonblank(name, "Log attribute name")
        if not isinstance(value, str | int | float | bool | None):
            raise TypeError("Log attribute values must be scalar")
        selected[key] = value
    return MappingProxyType(selected)


__all__ = [
    "Event",
    "Log",
    "Span",
    "Started",
    "Terminated",
    "TerminationError",
    "Usage",
]
