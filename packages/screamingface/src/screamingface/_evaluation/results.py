"""Decode Engine Candidate outcomes into the stable public Report."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping, Sequence
from typing import Literal

from screamingface._core.ports import _RunOutcome
from screamingface._evaluation.model import Candidate, _Evaluation
from screamingface.errors import ExecutionError
from screamingface.report import (
    CandidateResult,
    CaseGrade,
    CaseResult,
    Check,
    Evidence,
    EvidenceProducer,
    Failure,
    MemberResult,
    Report,
    Usage,
)
from screamingface.warnings import CoverageWarning


def report_from_outcomes(
    evaluation: _Evaluation,
    outcomes: tuple[tuple[Candidate, _RunOutcome], ...],
) -> Report:
    """Build one stable Report from independently executed Candidate roots."""

    candidates = tuple(
        _candidate_result(evaluation, candidate, outcome) for candidate, outcome in outcomes
    )
    return Report(
        benchmark=evaluation.benchmark,
        case_count=evaluation.case_count,
        candidates=candidates,
    )


def _candidate_result(
    evaluation: _Evaluation,
    candidate: Candidate,
    outcome: _RunOutcome,
) -> CandidateResult:
    try:
        payload = json.loads(outcome.result_body)
    except json.JSONDecodeError as exc:
        raise ExecutionError("SF Engine Candidate result must be JSON") from exc
    value = _mapping(payload, "Candidate result")
    _keys(
        value,
        required={
            "schema",
            "benchmark_id",
            "benchmark_revision",
            "case_count",
            "score",
            "metrics",
            "cases",
            "failures",
        },
        label="Candidate result",
    )
    if value.get("schema") != "screamingface.candidate-result.v1":
        raise ExecutionError("SF Engine Candidate result schema is unsupported")
    if value.get("benchmark_id") != evaluation.benchmark.id:
        raise ExecutionError("SF Engine Candidate result has the wrong Benchmark id")
    if value.get("benchmark_revision") != evaluation.benchmark.revision:
        raise ExecutionError("SF Engine Candidate result has the wrong Benchmark revision")
    if _positive_integer(value.get("case_count"), "Candidate case_count") != evaluation.case_count:
        raise ExecutionError("SF Engine Candidate result has the wrong case count")
    score_value = value.get("score")
    score = None if score_value is None else _number(score_value, "Candidate score")
    metrics = _metrics(value.get("metrics"))
    _warn_on_coverage(candidate.name, metrics)
    try:
        cases = _cases(_required(value, "cases", "Candidate result"))
        if len(cases) != evaluation.case_count:
            raise ExecutionError("SF Engine Candidate result has the wrong number of Cases")
        failures = _failures(_required(value, "failures", "Candidate result"), "Candidate failures")
        return CandidateResult(
            run_id=outcome.run_id,
            started_at=outcome.started_at,
            completed_at=outcome.completed_at,
            name=candidate.name,
            kind=candidate.kind,
            url4=candidate.url4,
            models=candidate.models,
            operations=candidate.operations,
            score=score,
            metrics=metrics,
            cases=cases,
            members=tuple(
                MemberResult(
                    operation_id=member.operation_id,
                    name=member.name,
                    kind=member.kind,
                    models=member.models,
                    failures=None,
                    duration_ms=None,
                    usage=None,
                )
                for member in candidate.members
            ),
            failures=failures,
            usage=outcome.root_usage or Usage(),
        )
    except (TypeError, ValueError) as exc:
        raise ExecutionError(f"SF Engine Candidate result is invalid: {exc}") from exc


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ExecutionError(f"{label} must be an object")
    return value


def _metrics(value: object) -> dict[str, float]:
    raw = _mapping(value, "Candidate metrics")
    return {str(name): _number(metric, f"metric {name!r}") for name, metric in raw.items()}


def _cases(value: object) -> tuple[CaseResult, ...]:
    return tuple(_case_result(item) for item in _sequence(value, "Candidate cases"))


def _case_result(value: object) -> CaseResult:
    raw = _mapping(value, "Case Result")
    _keys(
        raw,
        required={
            "case_id",
            "input",
            "output",
            "finish_reason",
            "grade",
            "failures",
            "metadata",
        },
        label="Case Result",
    )
    case_id = _positive_integer(raw.get("case_id"), "Case Result case_id")
    grade_value = _required(raw, "grade", "Case Result")
    grade = None if grade_value is None else _case_grade(grade_value)
    failures = _failures(_required(raw, "failures", "Case Result"), "Case Result failures")
    if any(failure.case_id not in {None, case_id} for failure in failures):
        raise ExecutionError("Case Result contains a Failure for another Case")
    finish_reason_value = _required(raw, "finish_reason", "Case Result")
    return CaseResult(
        case_id=case_id,
        input=_required(raw, "input", "Case Result"),
        output=_required(raw, "output", "Case Result"),
        finish_reason=(
            None
            if finish_reason_value is None
            else _text(finish_reason_value, "Case Result finish_reason")
        ),
        grade=grade,
        failures=failures,
        metadata=_mapping(_required(raw, "metadata", "Case Result"), "Case Result metadata"),
    )


def _case_grade(value: object) -> CaseGrade:
    raw = _mapping(value, "Case Grade")
    _keys(raw, required={"method", "score", "metrics", "checks"}, label="Case Grade")
    score_value = raw.get("score")
    return CaseGrade(
        method=_text(raw.get("method"), "Case Grade method"),
        score=None if score_value is None else _number(score_value, "Case Grade score"),
        metrics=_mapping(raw.get("metrics"), "Case Grade metrics"),
        checks=tuple(_check(item) for item in _sequence(raw.get("checks"), "Case Grade checks")),
    )


def _check(value: object) -> Check:
    raw = _mapping(value, "Check")
    _keys(
        raw,
        required={"type", "id", "label", "evidence", "metadata"},
        optional={"outcome", "score"},
        label="Check",
    )
    score_value = raw.get("score")
    return Check(
        type=_text(raw.get("type"), "Check type"),
        id=_text(raw.get("id"), "Check id"),
        label=_text(raw.get("label"), "Check label"),
        evidence=tuple(
            _evidence(item) for item in _sequence(raw.get("evidence"), "Check evidence")
        ),
        outcome=raw.get("outcome"),
        score=None if score_value is None else _number(score_value, "Check score"),
        metadata=_mapping(raw.get("metadata"), "Check metadata"),
    )


def _evidence(value: object) -> Evidence:
    raw = _mapping(value, "Evidence")
    _keys(
        raw,
        required={"sequence", "producer", "valid", "raw_output", "metadata"},
        optional={"outcome", "explanation"},
        label="Evidence",
    )
    producer = _mapping(raw.get("producer"), "Evidence producer")
    _keys(producer, required={"type", "id"}, label="Evidence producer")
    valid = raw.get("valid")
    if not isinstance(valid, bool):
        raise ExecutionError("Evidence valid must be boolean")
    return Evidence(
        sequence=_positive_integer(raw.get("sequence"), "Evidence sequence"),
        producer=EvidenceProducer(
            type=_producer_type(producer.get("type")),
            id=_text(producer.get("id"), "Evidence producer id"),
        ),
        valid=valid,
        outcome=raw.get("outcome"),
        explanation=_optional_text(raw.get("explanation"), "Evidence explanation"),
        raw_output=_required(raw, "raw_output", "Evidence"),
        metadata=_mapping(raw.get("metadata"), "Evidence metadata"),
    )


def _failures(value: object, label: str) -> tuple[Failure, ...]:
    return tuple(_failure(item) for item in _sequence(value, label))


def _failure(value: object) -> Failure:
    raw = _mapping(value, "Failure")
    _keys(
        raw,
        required={"stage", "code", "message"},
        optional={"retryable", "operation_id", "case_id", "metadata"},
        label="Failure",
    )
    retryable = raw.get("retryable")
    if retryable is not None and not isinstance(retryable, bool):
        raise ExecutionError("Failure retryable must be boolean or null")
    operation_id = _optional_text(raw.get("operation_id"), "Failure operation_id")
    return Failure(
        stage=_failure_stage(raw.get("stage")),
        code=_text(raw.get("code"), "Failure code"),
        message=_text(raw.get("message"), "Failure message"),
        retryable=retryable,
        operation_id=operation_id,
        case_id=_failure_case_id(raw.get("case_id")),
        metadata=_mapping(raw.get("metadata", {}), "Failure metadata"),
    )


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise ExecutionError(f"{label} must be an array")
    return value


def _required(value: Mapping[str, object], key: str, label: str) -> object:
    if key not in value:
        raise ExecutionError(f"{label} is missing {key!r}")
    return value[key]


def _keys(
    value: Mapping[str, object],
    *,
    required: set[str],
    label: str,
    optional: set[str] | None = None,
) -> None:
    present = set(value)
    if missing := sorted(required - present):
        raise ExecutionError(f"{label} is missing {missing[0]!r}")
    if unknown := sorted(present - required - (optional or set())):
        raise ExecutionError(f"{label} contains unsupported field {unknown[0]!r}")


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ExecutionError(f"{label} must be a positive integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionError(f"{label} must be non-empty text")
    return value


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _producer_type(value: object) -> Literal["model", "deterministic"]:
    if value == "model":
        return "model"
    if value == "deterministic":
        return "deterministic"
    raise ExecutionError("Evidence producer type is unsupported")


def _failure_stage(value: object) -> Literal["candidate", "grading", "aggregation"]:
    if value == "candidate":
        return "candidate"
    if value == "grading":
        return "grading"
    if value == "aggregation":
        return "aggregation"
    raise ExecutionError("Failure stage is unsupported")


def _failure_case_id(value: object) -> int | str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ExecutionError("Failure case_id must be a string, integer, or null")


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ExecutionError(f"{label} must be numeric")
    return float(value)


def _warn_on_coverage(candidate_name: str, metrics: Mapping[str, float]) -> None:
    coverage = metrics.get("coverage")
    target = metrics.get("coverage_target")
    if coverage is None or target is None or coverage >= target:
        return
    accepted = metrics.get("verdicts_accepted")
    expected = metrics.get("verdicts_expected")
    counts = ""
    if accepted is not None and expected is not None:
        counts = f"{int(accepted)}/{int(expected)} verdicts accepted; "
    warnings.warn(
        f"Candidate {candidate_name!r}: {counts}coverage {coverage:.1%} is below the "
        f"Benchmark target {target:.1%}. The score excludes rejected verdicts.",
        CoverageWarning,
        stacklevel=3,
    )


__all__: list[str] = []
