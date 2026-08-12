"""Cross-Benchmark Candidate finalization and score publication policy."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from url4_cloud.benchmarks.contract import (
    CandidateResult,
    CaseGrade,
    CaseId,
    CaseResult,
    Failure,
    validate_case_id,
    validate_finish_reason,
)


class SelectedCase(BaseModel):
    """One immutable public Case selected by the Benchmark protocol."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    case_id: CaseId
    input: str = Field(min_length=1)
    metadata: dict[str, Any]

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: CaseId) -> CaseId:
        validated = validate_case_id(value)
        assert validated is not None
        return validated


@dataclass(frozen=True, slots=True)
class CandidateRefusal:
    """Exact provider refusal fields recovered after URL4 error collection."""

    text: str
    finish_reason: str | None


@dataclass(frozen=True, slots=True)
class PublicError:
    """Safe operational diagnostics suitable for the public result contract."""

    kind: str | None
    code: str
    message: str
    retryable: bool | None


@dataclass(frozen=True, slots=True)
class CandidateScore:
    """A Benchmark scorer's result after every selected Case graded successfully."""

    # HealthBench's official penalty-bearing result can be negative.
    score: float
    metrics: dict[str, Any]


Scorer = Callable[[Sequence[CaseResult]], CandidateScore]


def finalize_candidate_result(
    *,
    benchmark_id: str,
    benchmark_revision: str,
    selected_cases: Sequence[SelectedCase | Mapping[str, Any]],
    cases: Sequence[CaseResult | Mapping[str, Any]],
    scorer: Scorer,
    failures: Sequence[Failure | Mapping[str, Any]] = (),
) -> CandidateResult:
    """Preserve Cases and publish a score only for a complete successful run."""

    selection = [
        case if isinstance(case, SelectedCase) else SelectedCase.model_validate(case)
        for case in selected_cases
    ]
    produced_cases = [
        case if isinstance(case, CaseResult) else CaseResult.model_validate(case) for case in cases
    ]
    typed_failures = [
        failure if isinstance(failure, Failure) else Failure.model_validate(failure)
        for failure in failures
    ]
    selected_ids = [case.case_id for case in selection]
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("selected Case sequence cannot contain duplicate case_id values")
    produced_ids = [case.case_id for case in produced_cases]
    if len(produced_ids) != len(set(produced_ids)):
        raise ValueError("CandidateResult cannot contain duplicate case_id values")
    unexpected = set(produced_ids) - set(selected_ids)
    if unexpected:
        raise ValueError(
            f"CandidateResult contains unselected case_id values {sorted(unexpected, key=str)!r}"
        )
    produced_by_id = {case.case_id: case for case in produced_cases}
    typed_cases = [
        produced_by_id.get(selected.case_id)
        or CaseResult(
            status="failed",
            case_id=selected.case_id,
            input=selected.input,
            output=None,
            finish_reason=None,
            refusal=None,
            grade=None,
            failures=[
                Failure(
                    stage="aggregation",
                    code="case_result_missing",
                    message="the selected Case produced no Case Result",
                    retryable=None,
                    case_id=selected.case_id,
                    metadata={},
                )
            ],
            metadata=selected.metadata,
        )
        for selected in selection
    ]

    complete = not typed_failures and all(case.status == "scored" for case in typed_cases)
    scored = scorer(tuple(typed_cases)) if complete else None
    return CandidateResult(
        benchmark_id=benchmark_id,
        benchmark_revision=benchmark_revision,
        case_count=len(typed_cases),
        score=scored.score if scored is not None else None,
        metrics=scored.metrics if scored is not None else {},
        cases=typed_cases,
        failures=typed_failures,
    )


def collected_provider_refusal(row: object) -> CandidateRefusal | None:
    """Read exact refusal fields carried through URL4's collected-error boundary."""

    error = row.get("error") if isinstance(row, Mapping) else None
    if not isinstance(error, Mapping) or error.get("kind") != "ProviderRefusal":
        return None
    raw = error.get("message")
    return _decode_provider_refusal(raw) if isinstance(raw, str) else None


def _decode_provider_refusal(raw: str) -> CandidateRefusal | None:
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    fields = _provider_refusal_fields(payload)
    return CandidateRefusal(*fields) if fields is not None else None


def _provider_refusal_fields(payload: object) -> tuple[str, str | None] | None:
    refusal = payload.get("refusal") if isinstance(payload, Mapping) else None
    if (
        not isinstance(payload, Mapping)
        or set(payload) != {"refusal", "finish_reason"}
        or not isinstance(refusal, str)
        or not refusal.strip()
    ):
        return None
    finish_reason = payload.get("finish_reason")
    try:
        typed_finish_reason = validate_finish_reason(finish_reason)
    except ValueError:
        return None
    return refusal, typed_finish_reason


def public_error(
    error: Mapping[str, Any],
    *,
    default_code: str,
    default_message: str,
) -> PublicError:
    """Retain useful error fields without publishing runner internals or credentials."""

    kind = _public_identifier(error.get("kind"))
    code = _public_identifier(error.get("code")) or default_code
    message = _public_message(error.get("message"), default=default_message)
    retryable = error.get("retryable")
    if not isinstance(retryable, bool):
        permanent = error.get("permanent")
        retryable = not permanent if isinstance(permanent, bool) else None
    return PublicError(kind=kind, code=code, message=message, retryable=retryable)


def _public_identifier(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()[:80]
    return normalized if re.fullmatch(r"[A-Za-z0-9_.:-]+", normalized) else None


def _public_message(value: object, *, default: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    normalized = " ".join(value.split())[:200]
    lowered = normalized.casefold()
    internal_markers = (
        "traceback (most recent call last)",
        'file "',
        "/users/",
        "/private/",
        "/tmp/",
        "/var/",
        "/home/",
    )
    return (
        default
        if any(marker in lowered for marker in internal_markers)
        or any(pattern.search(normalized) for pattern in _SENSITIVE_ERROR_PATTERNS)
        else normalized
    )


_SENSITIVE_ERROR_PATTERNS = (
    re.compile(r"(?i)(?:^|\s)[a-z]:\\"),
    re.compile(
        r"(?i)(?:^|[^A-Za-z0-9])(?:[A-Za-z0-9]+[_-])*"
        r"(?:authorization|password|passwd|pwd|secret|token|cookie|api[_-]?key|"
        r"access[_-]?key)\s*[:=]"
    ),
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def scored_case_result(
    *,
    selected_case: SelectedCase,
    output: str,
    finish_reason: str | None,
    grade: CaseGrade | Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> CaseResult:
    """Construct one scored Case without exposing the wire envelope to adapters."""

    typed_grade = grade if isinstance(grade, CaseGrade) else CaseGrade.model_validate(grade)
    return CaseResult(
        status="scored",
        case_id=selected_case.case_id,
        input=selected_case.input,
        output=output,
        finish_reason=finish_reason,
        refusal=None,
        grade=typed_grade,
        failures=[],
        metadata=_case_metadata(selected_case, metadata),
    )


def failed_case_result(
    *,
    selected_case: SelectedCase,
    failures: Sequence[Failure | Mapping[str, Any]],
    output: str | None = None,
    finish_reason: str | None = None,
    grade: CaseGrade | Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CaseResult:
    """Construct one failed Case while retaining any safe partial grading evidence."""

    typed_grade = (
        grade if isinstance(grade, CaseGrade) or grade is None else CaseGrade.model_validate(grade)
    )
    typed_failures = [
        failure if isinstance(failure, Failure) else Failure.model_validate(failure)
        for failure in failures
    ]
    return CaseResult(
        status="failed",
        case_id=selected_case.case_id,
        input=selected_case.input,
        output=output,
        finish_reason=finish_reason,
        refusal=None,
        grade=typed_grade,
        failures=typed_failures,
        metadata=_case_metadata(selected_case, metadata),
    )


def refused_case_result(
    *,
    selected_case: SelectedCase,
    refusal: str,
    finish_reason: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CaseResult:
    """Construct the one canonical refused Case shape without invoking grading."""

    return CaseResult(
        status="refused",
        case_id=selected_case.case_id,
        input=selected_case.input,
        output=None,
        finish_reason=finish_reason,
        refusal=refusal,
        grade=None,
        failures=[
            Failure(
                stage="candidate",
                code="provider_refusal",
                message="the provider refused this Candidate request",
                retryable=False,
                case_id=selected_case.case_id,
                metadata={},
            )
        ],
        metadata=_case_metadata(selected_case, metadata),
    )


def _case_metadata(
    selected_case: SelectedCase, metadata: Mapping[str, Any] | None
) -> dict[str, Any]:
    return {**selected_case.metadata, **dict(metadata or {})}


__all__ = [
    "CandidateScore",
    "CandidateRefusal",
    "Scorer",
    "SelectedCase",
    "collected_provider_refusal",
    "failed_case_result",
    "finalize_candidate_result",
    "public_error",
    "refused_case_result",
    "scored_case_result",
]
