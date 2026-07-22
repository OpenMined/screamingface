"""URL4 adapters for deterministic ScreamingFace report aggregation."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from statistics import fmean
from typing import NoReturn

from url4 import Request, ResolutionError

from screamingface_engine.evaluation_events import emit_progress
from screamingface_engine.graders import CASE_GRADE_SCHEMA

MEAN_ROUTE = "/aggregators/mean/1"
REPORT_SCHEMA = "screamingface.report.v1"
CANDIDATE_MEAN_ROUTE = "/aggregators/candidate-mean/1"
CANDIDATE_CASE_SCHEMA = "screamingface.candidate-case-results.v1"
STUDY_REPORT_SCHEMA = "screamingface.study-report.v1"


def mean(request: Request) -> str:
    """Aggregate URL4 iteration rows over one strict paired case set."""

    if request.context:
        _invalid("mean does not accept context")
    if request.params:
        _invalid(f"mean does not accept parameters: {sorted(request.params)}")
    rows = _rows(request.intent)
    emit_progress("aggregating", "started", f"Aggregating {len(rows)} benchmark cases")
    successes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for position, row in enumerate(rows, 1):
        error = row.get("error")
        if error is not None:
            failures.append(_failure(error, position))
            continue
        successes.append(_case_grade(row, position))
    if not successes:
        message = failures[0]["message"] if failures else "benchmark produced no grade rows"
        raise ResolutionError(
            str(message),
            code="benchmark_evaluation_failed",
        )

    benchmark_id = successes[0]["benchmark_id"]
    member_models = _member_models(successes[0])
    for row in successes[1:]:
        if row["benchmark_id"] != benchmark_id:
            _invalid("case grades disagree on benchmark ID")
        if _member_models(row) != member_models:
            _invalid("case grades disagree on Recipe members")

    recipe_score = fmean(_score(row["recipe"], "Recipe grade") for row in successes)
    recipe_metrics = _mean_metrics(
        [row["recipe"] for row in successes],
        "Recipe grade",
    )
    members = {
        member_id: {
            "model": model,
            "score": fmean(
                _score(_member(row, member_id), f"member {member_id!r}") for row in successes
            ),
            "metrics": _mean_metrics(
                [_member(row, member_id) for row in successes],
                f"member {member_id!r}",
            ),
        }
        for member_id, model in member_models.items()
    }
    baseline = max(float(member["score"]) for member in members.values())
    n_cases = len(rows)
    n_scored = len(successes)
    payload = {
        "schema": REPORT_SCHEMA,
        "benchmark_id": benchmark_id,
        "case_ids": [
            row["case_id"] if "case_id" in row else f"row_{position}"
            for position, row in enumerate(rows, 1)
        ],
        "n_cases": n_cases,
        "n_scored": n_scored,
        "coverage": n_scored / n_cases,
        "score": recipe_score,
        "baseline": baseline,
        "gain": recipe_score - baseline,
        "members": members,
        "metrics": recipe_metrics,
        "failures": failures,
        "complete": not failures,
    }
    return json.dumps(payload, allow_nan=False, separators=(",", ":"))


def candidate_mean(request: Request) -> str:
    """Aggregate independently graded candidate roots over one shared case set."""

    if request.context:
        _invalid("candidate mean does not accept context")
    if request.params:
        _invalid(f"candidate mean does not accept parameters: {sorted(request.params)}")
    rows = _rows(request.intent)
    emit_progress("aggregating", "started", f"Aggregating {len(rows)} candidate case rows")
    if any(row.get("error") is not None for row in rows):
        first = next(row["error"] for row in rows if row.get("error") is not None)
        raise ResolutionError(
            str(_failure(first, 1)["message"]),
            code="benchmark_evaluation_failed",
        )
    decoded = [_candidate_case(row, position) for position, row in enumerate(rows, 1)]
    benchmark_id = decoded[0]["benchmark_id"]
    first_candidates = decoded[0]["candidates"]
    assert isinstance(first_candidates, Mapping)
    candidate_names = tuple(first_candidates)
    for row in decoded[1:]:
        if row["benchmark_id"] != benchmark_id:
            _invalid("candidate rows disagree on benchmark ID")
        row_candidates = row["candidates"]
        assert isinstance(row_candidates, Mapping)
        if tuple(row_candidates) != candidate_names:
            _invalid("candidate rows disagree on candidate order")

    candidates: dict[str, dict[str, object]] = {}
    for name in candidate_names:
        grades: list[Mapping[str, object]] = []
        failures: list[dict[str, object]] = []
        for row in decoded:
            row_candidates = row["candidates"]
            assert isinstance(row_candidates, Mapping)
            raw = row_candidates[name]
            assert isinstance(raw, Mapping)
            failure = raw["failure"]
            if failure is not None:
                failures.append(_candidate_failure(failure, str(row["case_id"])))
                continue
            grades.append(raw)
        n_cases = len(decoded)
        n_scored = len(grades)
        candidates[name] = {
            "n_cases": n_cases,
            "n_scored": n_scored,
            "coverage": n_scored / n_cases,
            "score": (None if not grades else fmean(_score(value, name) for value in grades)),
            "metrics": ({} if not grades else _mean_metrics(list(grades), name)),
            "failures": failures,
            "complete": not failures,
        }
        status = "completed" if grades else "skipped"
        label = (
            f"Finalized {name} ({n_scored}/{n_cases} cases scored)"
            if grades
            else f"Unavailable {name} (0/{n_cases} cases scored)"
        )
        emit_progress(
            "candidate",
            status,
            label,
            operation_id=f"candidate:{name}",
        )
    payload = {
        "schema": STUDY_REPORT_SCHEMA,
        "benchmark_id": benchmark_id,
        "case_ids": [row["case_id"] for row in decoded],
        "candidates": candidates,
        "complete": all(not value["failures"] for value in candidates.values()),
    }
    emit_progress("aggregating", "completed", "Aggregated candidate study")
    return json.dumps(payload, allow_nan=False, separators=(",", ":"))


def _candidate_case(row: dict[str, object], position: int) -> dict[str, object]:
    expected = {"schema", "benchmark_id", "case_id", "candidates"}
    if set(row) != expected or row.get("schema") != CANDIDATE_CASE_SCHEMA:
        _invalid(f"row {position} is not a {CANDIDATE_CASE_SCHEMA!r} object")
    _nonblank(row["benchmark_id"], f"row {position} benchmark ID")
    _nonblank(row["case_id"], f"row {position} case ID")
    raw = row["candidates"]
    if not isinstance(raw, Mapping) or not raw:
        _invalid(f"row {position} candidates must be a non-empty object")
    for name, value in raw.items():
        _nonblank(name, f"row {position} candidate name")
        if not isinstance(value, Mapping) or set(value) != {"score", "metrics", "failure"}:
            _invalid(f"row {position} candidate {name!r} has an invalid result")
        failure = value["failure"]
        if failure is None:
            _score(value, f"candidate {name!r}")
            _grade_metrics(value, f"candidate {name!r}")
        elif value["score"] is not None or value["metrics"] != {}:
            _invalid(f"row {position} failed candidate {name!r} cannot have scores")
    return row


def _candidate_failure(value: object, case_id: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {"kind", "message", "status", "code"}:
        _invalid("candidate failure must contain kind, message, status, and code")
    kind = _nonblank(value["kind"], "candidate failure kind")
    if kind not in {"connection", "timeout", "http", "url4", "protocol", "skipped"}:
        _invalid(f"candidate failure has unknown kind {kind!r}")
    status = value["status"]
    if status is not None and (
        isinstance(status, bool) or not isinstance(status, int) or status < 100
    ):
        _invalid("candidate failure status must be an HTTP status or null")
    code = value["code"]
    if code is not None:
        code = _nonblank(code, "candidate failure code")
    return {
        "case_id": case_id,
        "kind": kind,
        "message": _nonblank(value["message"], "candidate failure message"),
        "status": status,
        "code": code,
    }


def _rows(text: str) -> list[dict[str, object]]:
    if not text:
        _invalid("mean intent must be a JSON array")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        _invalid("mean intent must be a JSON array")
    if not isinstance(value, list) or not value:
        _invalid("mean intent must be a non-empty JSON array")
    if not all(isinstance(row, dict) for row in value):
        _invalid("mean rows must be JSON objects")
    return value


def _case_grade(row: dict[str, object], position: int) -> dict[str, object]:
    expected = {"schema", "benchmark_id", "case_id", "recipe", "members"}
    if set(row) != expected or row.get("schema") != CASE_GRADE_SCHEMA:
        _invalid(f"row {position} is not a {CASE_GRADE_SCHEMA!r} object")
    if not isinstance(row["recipe"], Mapping) or not isinstance(row["members"], Mapping):
        _invalid(f"row {position} grades must be objects")
    _nonblank(row["benchmark_id"], f"row {position} benchmark ID")
    _nonblank(row["case_id"], f"row {position} case ID")
    return row


def _member_models(row: Mapping[str, object]) -> dict[str, str]:
    raw = row["members"]
    assert isinstance(raw, Mapping)
    if not raw:
        _invalid("case grade members must not be empty")
    models: dict[str, str] = {}
    for position, (member_id, value) in enumerate(raw.items(), 1):
        if member_id != f"member_{position}" or not isinstance(value, Mapping):
            _invalid("case grade members must be contiguous member_1 through member_n")
        models[member_id] = _nonblank(value.get("model"), f"member {member_id!r} model")
    return models


def _member(row: Mapping[str, object], member_id: str) -> Mapping[str, object]:
    members = row["members"]
    assert isinstance(members, Mapping)
    value = members[member_id]
    assert isinstance(value, Mapping)
    return value


def _score(value: object, label: str) -> float:
    if not isinstance(value, Mapping):
        _invalid(f"{label} must be an object")
    score = value.get("score")
    if isinstance(score, bool) or not isinstance(score, int | float):
        _invalid(f"{label} score must be numeric")
    normalized = float(score)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        _invalid(f"{label} score must be finite and between 0 and 1")
    return normalized


def _mean_metrics(values: list[object], label: str) -> dict[str, float]:
    decoded = [_grade_metrics(value, label) for value in values]
    names = tuple(decoded[0])
    if any(tuple(metrics) != names for metrics in decoded[1:]):
        _invalid(f"{label} metrics disagree across cases")
    return {name: fmean(metrics[name] for metrics in decoded) for name in names}


def _grade_metrics(value: object, label: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        _invalid(f"{label} must be an object")
    raw = value.get("metrics")
    if not isinstance(raw, Mapping):
        _invalid(f"{label} metrics must be an object")
    metrics: dict[str, float] = {}
    for name, metric in raw.items():
        key = _nonblank(name, f"{label} metric name")
        if isinstance(metric, bool) or not isinstance(metric, int | float):
            _invalid(f"{label} metric {key!r} must be numeric")
        normalized = float(metric)
        if not math.isfinite(normalized):
            _invalid(f"{label} metric {key!r} must be finite")
        metrics[key] = normalized
    return metrics


def _failure(value: object, position: int) -> dict[str, object]:
    if not isinstance(value, Mapping):
        _invalid(f"row {position} error must be an object")
    kind = _nonblank(value.get("kind"), f"row {position} error kind")
    message = _nonblank(value.get("message"), f"row {position} error message")
    return {
        "case_id": f"row_{position}",
        "kind": "url4",
        "message": f"{kind}: {message}",
        "status": None,
        "code": "resolution_failed",
    }


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{label} must be a non-blank string")
    return value.strip()


def _invalid(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_source", permanent=True)


__all__ = [
    "CANDIDATE_CASE_SCHEMA",
    "CANDIDATE_MEAN_ROUTE",
    "MEAN_ROUTE",
    "REPORT_SCHEMA",
    "STUDY_REPORT_SCHEMA",
    "candidate_mean",
    "mean",
]
