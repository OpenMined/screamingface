"""Build auditable DRACO Case Results from Engine-bound checks and evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from url4_cloud.benchmarks.draco.errors import AggregateError
from url4_cloud.benchmarks.draco.scoring import flatten_criteria, score_case
from url4_cloud.benchmarks.draco.validation import optional_integer
from url4_cloud.benchmarks.draco.verdict import SCHEMA as VERDICT_SCHEMA

COVERAGE_TARGET = 0.95


def group_runs(verdicts: Sequence[Mapping[str, Any]]) -> list[dict[str, bool]]:
    """Split flat verdicts into one dict per judge pass, in sequence order.

    INVARIANT: the paper scores each pass independently and then means the passes. Majority-voting
    first would erase the judge-disagreement signal. A criterion with fewer verdicts has no entry
    in the later runs, so it drops out rather than becoming an UNMET.
    """
    runs: list[dict[str, bool]] = []
    for verdict in verdicts:
        criterion_id = verdict.get("criterion_id") or verdict.get("id")
        sequence = optional_integer(verdict.get("sequence"))
        if criterion_id is None or sequence is None or sequence < 1:
            continue
        index = sequence - 1
        while len(runs) <= index:
            runs.append({})
        runs[index][str(criterion_id)] = str(verdict.get("criterion_status", "")).upper() == "MET"
    return runs


def valid_verdicts(
    rubric: Mapping[str, Any], verdicts: Sequence[Mapping[str, Any]], case_id: int
) -> list[dict[str, Any]]:
    """Keep strict verdicts for criterion ids owned by this case's rubric."""
    expected = {str(criterion["id"]) for criterion in flatten_criteria(rubric)}
    accepted: list[dict[str, Any]] = []
    for verdict in verdicts:
        criterion_id = verdict.get("criterion_id") or verdict.get("id")
        status = str(verdict.get("criterion_status", "")).upper()
        if (
            verdict.get("schema") != VERDICT_SCHEMA
            or verdict.get("valid") is not True
            or optional_integer(verdict.get("case_id")) != case_id
            or str(criterion_id) not in expected
            or status not in {"MET", "UNMET"}
            or (optional_integer(verdict.get("sequence")) or 0) < 1
            or verdict.get("producer_type") != "model"
            or not isinstance(verdict.get("producer_id"), str)
            or not isinstance(verdict.get("raw_output"), str)
        ):
            continue
        accepted.append({**verdict, "criterion_id": str(criterion_id), "criterion_status": status})
    return accepted


def scored_case_result(
    case_record: Mapping[str, Any],
    rubric: Mapping[str, Any],
    check_records: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    verdicts: Sequence[Mapping[str, Any]],
    judge_passes: int,
    criterion_count: int | None,
) -> dict[str, Any]:
    """Build one scored or coverage-failed Case Result."""
    case_id, criteria_expected = _expected_criteria(case_record, rubric, criterion_count)
    expected = criteria_expected * judge_passes
    accepted = len(verdicts)
    scored = score_case(rubric, group_runs(verdicts), criteria_expected=criteria_expected)
    coverage = (accepted / expected) if expected else 0.0
    metrics = {
        "normalized_score_sd": scored["normalized_score_sd"],
        "pass_rate": scored["pass_rate"],
        "pass_rate_sd": scored["pass_rate_sd"],
        "accuracy": scored["accuracy"],
        "accuracy_pass_rate": scored["accuracy_pass_rate"],
        "axis_scores": scored["axis_scores"],
        "axis_pass_rates": scored["axis_pass_rates"],
        "coverage": round(coverage, 4),
        "coverage_sd": scored["coverage_sd"],
        "n_runs": scored["n_runs"],
        "verdicts_expected": expected,
        "verdicts_accepted": accepted,
        "verdicts_rejected": max(expected - accepted, 0),
        "verdicts_invalid": max(len(records) - accepted, 0),
        "verdicts_missing": max(expected - len(records), 0),
    }
    failures: list[dict[str, Any]] = []
    score: float | None = scored["normalized_score"]
    if coverage < COVERAGE_TARGET:
        score = None
        failures.append(
            {
                "stage": "grading",
                "code": "insufficient_judge_coverage",
                "message": (
                    f"Judge coverage {coverage:.1%} is below the required {COVERAGE_TARGET:.0%}"
                ),
                "retryable": None,
                "case_id": case_id,
                "metadata": {
                    "coverage": round(coverage, 4),
                    "coverage_target": COVERAGE_TARGET,
                },
            }
        )
    return _case_result(
        case_record,
        score=score,
        metrics=metrics,
        checks=_checks(case_id, rubric, check_records, records, criteria_expected),
        failures=failures,
    )


def incomplete_case_result(
    case_record: Mapping[str, Any],
    rubric: Mapping[str, Any],
    check_records: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    judge_passes: int,
    criterion_count: int | None,
    failure: Mapping[str, Any],
) -> dict[str, Any]:
    """Retain auditable grading material when no Judge Evidence was scoreable."""
    case_id, criteria_expected = _expected_criteria(case_record, rubric, criterion_count)
    verdicts_expected = criteria_expected * judge_passes
    metrics = {
        "normalized_score_sd": 0.0,
        "pass_rate": 0.0,
        "pass_rate_sd": 0.0,
        # Nothing was judged, so the Factual Accuracy axis was never observed — unknown, not zero.
        "accuracy": None,
        "accuracy_pass_rate": None,
        "axis_scores": {},
        "axis_pass_rates": {},
        "coverage": 0.0,
        "coverage_sd": 0.0,
        "n_runs": 0,
        "verdicts_expected": verdicts_expected,
        "verdicts_accepted": 0,
        "verdicts_rejected": verdicts_expected,
        "verdicts_invalid": len(evidence),
        "verdicts_missing": max(verdicts_expected - len(evidence), 0),
    }
    return _case_result(
        case_record,
        score=None,
        metrics=metrics,
        checks=_checks(case_id, rubric, check_records, evidence, criteria_expected),
        failures=[dict(failure)],
    )


def failed_selected_case_result(
    selected_case: Mapping[str, Any], failure: Mapping[str, Any]
) -> dict[str, Any]:
    """Represent a selected Case that never produced a Candidate answer."""
    return {
        "case_id": int(selected_case["id"]),
        "input": selected_case["input"],
        "output": None,
        "finish_reason": None,
        "grade": None,
        "failures": [dict(failure)],
        "metadata": {
            key: value for key, value in selected_case.items() if key not in {"id", "input"}
        },
    }


def ungraded_case_result(
    case_record: Mapping[str, Any], failure: Mapping[str, Any]
) -> dict[str, Any]:
    """Retain an observed Candidate answer when private grading material is unavailable."""
    return {
        "case_id": int(case_record["case_id"]),
        "input": case_record["input"],
        "output": case_record["output"],
        "finish_reason": case_record["finish_reason"],
        "grade": None,
        "failures": [dict(failure)],
        "metadata": case_record.get("metadata", {}),
    }


def _expected_criteria(
    case_record: Mapping[str, Any],
    rubric: Mapping[str, Any],
    criterion_count: int | None,
) -> tuple[int, int]:
    case_id = int(case_record["case_id"])
    rubric_count = sum(1 for _ in flatten_criteria(rubric))
    if criterion_count is not None and criterion_count > rubric_count:
        raise AggregateError(
            f"criterion_count {criterion_count} exceeds Case {case_id} rubric size {rubric_count}"
        )
    return case_id, criterion_count if criterion_count is not None else rubric_count


def _case_result(
    case_record: Mapping[str, Any],
    *,
    score: float | None,
    metrics: Mapping[str, Any],
    checks: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Assemble the shared Case Result envelope once."""
    return {
        "case_id": int(case_record["case_id"]),
        "input": case_record["input"],
        "output": case_record["output"],
        "finish_reason": case_record["finish_reason"],
        "grade": {
            "method": "rubric",
            "score": score,
            "metrics": dict(metrics),
            "checks": [dict(check) for check in checks],
        },
        "failures": [dict(failure) for failure in failures],
        "metadata": case_record.get("metadata", {}),
    }


def _checks(
    case_id: int,
    rubric: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    criteria_expected: int,
) -> list[dict[str, Any]]:
    rubric_by_id = {str(criterion["id"]): criterion for criterion in flatten_criteria(rubric)}
    selected_ids = [str(record.get("criterion_id")) for record in records]
    if len(selected_ids) != criteria_expected or len(set(selected_ids)) != criteria_expected:
        raise AggregateError(
            f"Case {case_id} must carry exactly {criteria_expected} unique Engine-bound Checks"
        )
    try:
        selected = [rubric_by_id[criterion_id] for criterion_id in selected_ids]
    except KeyError as exc:
        raise AggregateError(
            f"Case {case_id} has an Engine-bound Check for unknown criterion {exc.args[0]!r}"
        ) from None
    by_id = {str(record.get("criterion_id")): record for record in records}
    checks: list[dict[str, Any]] = []
    for criterion in selected:
        criterion_id = str(criterion["id"])
        record = by_id.get(criterion_id)
        if record is None or optional_integer(record.get("case_id")) != case_id:
            raise AggregateError(f"Case {case_id} has no Engine-bound Check {criterion_id!r}")
        checks.append(
            {
                "type": "criterion",
                "id": criterion_id,
                "label": record["requirement"],
                "evidence": [
                    _evidence(item)
                    for item in sorted(
                        (
                            item
                            for item in evidence
                            if str(item.get("criterion_id")) == criterion_id
                        ),
                        key=lambda item: int(item["sequence"]),
                    )
                ],
                "metadata": {
                    "criterion_type": record["criterion_type"],
                    "weight": criterion["weight"],
                    "axis": criterion["axis"],
                },
            }
        )
    return checks


def _evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "sequence": int(record["sequence"]),
        "producer": {"type": record["producer_type"], "id": record["producer_id"]},
        "valid": record.get("valid") is True,
        "raw_output": record["raw_output"],
        "metadata": {},
    }
    if value["valid"]:
        value["outcome"] = record["criterion_status"]
        value["explanation"] = record["explanation"]
    else:
        value["metadata"] = {"rejection_reason": record.get("reason", "invalid")}
    return value
