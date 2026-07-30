"""Decode Engine Candidate outcomes into the stable public Report."""

from __future__ import annotations

import json
from collections.abc import Mapping

from screamingface._evaluation import Candidate, _Evaluation
from screamingface._ports import _RunOutcome
from screamingface.errors import ExecutionError
from screamingface.report import CandidateResult, Report, Usage


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
    if value.get("schema") != "screamingface.candidate-result.v1":
        raise ExecutionError("SF Engine Candidate result schema is unsupported")
    if value.get("benchmark_id") != evaluation.benchmark.id:
        raise ExecutionError("SF Engine Candidate result has the wrong Benchmark id")
    if value.get("manifest_digest") != evaluation.benchmark.manifest_digest:
        raise ExecutionError("SF Engine Candidate result has the wrong manifest digest")
    if value.get("case_count") != evaluation.case_count:
        raise ExecutionError("SF Engine Candidate result has the wrong case count")
    score = _number(value.get("score"), "Candidate score")
    metrics = _metrics(value.get("metrics"))
    failures = value.get("failures")
    if failures != []:
        raise ExecutionError("SF Engine Candidate result failures are not supported yet")
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
        members=(),
        failures=(),
        usage=outcome.root_usage or Usage(),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ExecutionError(f"{label} must be an object")
    return value


def _metrics(value: object) -> dict[str, float]:
    raw = _mapping(value, "Candidate metrics")
    return {str(name): _number(metric, f"metric {name!r}") for name, metric in raw.items()}


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ExecutionError(f"{label} must be numeric")
    return float(value)


__all__: list[str] = []
