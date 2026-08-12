"""Cross-Benchmark Candidate finalization and score publication policy."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from url4_cloud.benchmarks.contract import CandidateResult, CaseResult, Failure


class CandidateScore(BaseModel):
    """A Benchmark scorer's result after every selected Case graded successfully."""

    model_config = ConfigDict(extra="forbid", strict=True)

    # HealthBench's official penalty-bearing result can be negative.
    score: float = Field(le=1.0)
    metrics: dict[str, Any]

    @field_validator("score", mode="before")
    @classmethod
    def _validate_score(cls, value: object) -> object:
        if isinstance(value, bool) or isinstance(value, int | float) and not math.isfinite(value):
            raise ValueError("score must be a finite number")
        return value

    @model_validator(mode="after")
    def _require_canonical_metrics(self) -> CandidateScore:
        for key in ("pass_rate", "coverage"):
            value = self.metrics.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"CandidateScore metric {key!r} must be in [0, 1]")
        return self


Scorer = Callable[[Sequence[CaseResult]], CandidateScore]


def finalize_candidate_result(
    *,
    benchmark_id: str,
    benchmark_revision: str,
    cases: Sequence[CaseResult | Mapping[str, Any]],
    scorer: Scorer,
    failures: Sequence[Failure | Mapping[str, Any]] = (),
) -> CandidateResult:
    """Preserve Cases and publish a score only for a complete successful run."""

    typed_cases = [
        case if isinstance(case, CaseResult) else CaseResult.model_validate(case) for case in cases
    ]
    typed_failures = [
        failure if isinstance(failure, Failure) else Failure.model_validate(failure)
        for failure in failures
    ]
    case_ids = [case.case_id for case in typed_cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("CandidateResult cannot contain duplicate case_id values")

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


def collected_provider_refusal(row: object) -> str | None:
    """Read exact refusal text carried through URL4's collected-error boundary."""

    error = row.get("error") if isinstance(row, Mapping) else None
    if not isinstance(error, Mapping) or error.get("kind") != "ProviderRefusal":
        return None
    refusal = error.get("message")
    return refusal if isinstance(refusal, str) and refusal.strip() else None


def refused_case_result(
    *,
    case_id: int | str,
    input: str | None,
    refusal: str,
    finish_reason: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CaseResult:
    """Construct the one canonical refused Case shape without invoking grading."""

    return CaseResult(
        status="refused",
        case_id=case_id,
        input=input,
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
                case_id=case_id,
                metadata={},
            )
        ],
        metadata=dict(metadata or {}),
    )


__all__ = [
    "CandidateScore",
    "Scorer",
    "collected_provider_refusal",
    "finalize_candidate_result",
    "refused_case_result",
]
