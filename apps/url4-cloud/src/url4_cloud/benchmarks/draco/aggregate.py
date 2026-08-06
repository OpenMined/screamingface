"""The DRACO cross-row reducer — per-criterion verdicts in, Candidate Result out.

FEATURE: one url4 expression per Candidate ends in a cross-row reduce that turns every case's
judge verdicts into one scored result.
STORY: as a researcher, the number I publish is the DRACO paper's `normalized_score`.

Installed directly into each Runner world in the reducer position::

    (…iteration…)!/benchmarks/draco/<revision>/aggregate($rows)!'aggregate'

    context (row array)  →  the JSON array of every row's judge output
    intent ("aggregate") →  the fixed reduction operation

INVARIANT — the scoring formulas mirror `screamingface-benchmarks/benchmarking/graders/rubric.py`
(arXiv:2602.11685 §4.2) EXACTLY. Do not "improve" them. A different formula is a different
benchmark, and a leaderboard number computed here must mean what the paper says it means.

The expression this reducer serves runs the paper's `official` grading mode: ONE judge call per
CRITERION, five independent passes, and the judge blind to the weights and to the sibling
criteria. The Engine-owned Benchmark definition constructs that fan-out and this in-process
handler reduces the complete row collection without crossing an operating-system argv boundary.

AIDEV-NOTE — PROTOCOL CAVEATS, the two ways a run here still differs from the paper:

* `judge_reasoning: "low"` (arXiv:2602.11685 §4.2) is NOT carried until the gateway supports it.
  `reasoning_effort` is absent from the OpenRouter plugin's rule set, and the gateway fails
  closed on an unknown parameter, so
  sending it would turn every judge call into a 400 rather than a deviation. `judge_temperature`
  and `max_tokens` DO reach the model.
* Retrieval reaches EVERY answering route as of 2026-08-02, but by TWO different mechanisms
  (owner decision, same date): provider-side `native_web_search` on the OpenRouter routes that
  support it, and the runner-driven Tavily loop on `gemini-3.1-pro-preview`,
  `gemini-3-flash-preview`, `kimi-k2.6`, `deepseek-v4-pro`, and `qwen3.6-plus`. Both honour the
  same declared blocklist—verified live on both paths—but they are not the same search product,
  so a candidate that answered through Tavily and one that answered natively did not read the
  same web. A comparison ACROSS those two groups carries that caveat; the reference chart used
  neither exactly.

Neither is visible in the numbers this module emits. A score published as "DRACO-reproduced"
has to state both.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from url4_cloud.benchmarks.contract import CANDIDATE_RESULT_SCHEMA
from url4_cloud.benchmarks.draco.case_evaluation import decode_case_evaluation
from url4_cloud.benchmarks.draco.definition import JUDGE_PASSES, REVISION
from url4_cloud.benchmarks.draco.scoring import flatten_criteria, score_case
from url4_cloud.benchmarks.draco.verdict import SCHEMA as VERDICT_SCHEMA

COVERAGE_TARGET = 0.95


class AggregateError(ValueError):
    """The reducer's input is unusable — raised before any scoring."""


def group_runs(verdicts: Sequence[Mapping[str, Any]]) -> list[dict[str, bool]]:
    """Split flat verdicts into one dict per judge PASS, by order of appearance per criterion.

    INVARIANT: the paper scores each pass independently and then means the passes (§4.2).
    Majority-voting the verdicts first would collapse judge disagreement before it reaches the
    score and would make the reported spread meaningless — the spread IS the stability signal.

    A criterion with fewer verdicts than the others simply has no entry in the later runs, so
    it drops out of those runs' rubrics rather than becoming an UNMET.
    """
    runs: list[dict[str, bool]] = []
    for verdict in verdicts:
        criterion_id = verdict.get("criterion_id") or verdict.get("id")
        sequence = _as_int(verdict.get("sequence"))
        if criterion_id is None or sequence is None or sequence < 1:
            continue
        key = str(criterion_id)
        index = sequence - 1
        while len(runs) <= index:
            runs.append({})
        runs[index][key] = str(verdict.get("criterion_status", "")).upper() == "MET"
    return runs


def valid_verdicts(
    rubric: Mapping[str, Any], verdicts: Sequence[Mapping[str, Any]], case_id: int
) -> list[dict[str, Any]]:
    """Keep only strict verdicts for criterion ids owned by this case's rubric.

    Identifier binding already happened locally after the Judge call. Aggregation validates again
    as defense in depth: only a valid shared record owned by this Case may affect its score.
    """
    expected = {str(criterion["id"]) for criterion in flatten_criteria(rubric)}
    accepted: list[dict[str, Any]] = []
    for verdict in verdicts:
        criterion_id = verdict.get("criterion_id") or verdict.get("id")
        status = str(verdict.get("criterion_status", "")).upper()
        if (
            verdict.get("schema") != VERDICT_SCHEMA
            or verdict.get("valid") is not True
            or _as_int(verdict.get("case_id")) != case_id
            or str(criterion_id) not in expected
            or status not in {"MET", "UNMET"}
            or (_as_int(verdict.get("sequence")) or 0) < 1
            or verdict.get("producer_type") != "model"
            or not isinstance(verdict.get("producer_id"), str)
            or not isinstance(verdict.get("raw_output"), str)
        ):
            continue
        accepted.append({**verdict, "criterion_id": str(criterion_id), "criterion_status": status})
    return accepted


# --- the reduction ---------------------------------------------------------------


def aggregate(
    rows_json: str,
    rubrics: Mapping[int, Mapping[str, Any]],
    benchmark_id: str,
    *,
    selected_cases: Sequence[Mapping[str, Any]],
    judge_passes: int = JUDGE_PASSES,
    benchmark_revision: str = REVISION,
    criterion_count: int | None = None,
) -> dict[str, Any]:
    """Reduce the row array into a Candidate Result — one row per Case.

    INVARIANT: a case that produced no verdicts is EXCLUDED from the mean and named in
    ``failures`` — never scored 0.0. Scoring it zero would penalise the Candidate for a harness
    failure, the same class of error as counting an unjudged criterion as UNMET.
    """
    try:
        rows = json.loads(rows_json)
    except (TypeError, ValueError) as exc:
        raise AggregateError(f"reducer payload is not JSON: {exc}") from None
    if not isinstance(rows, list):
        raise AggregateError(f"reducer payload must be a JSON array, got {type(rows).__name__}")
    if isinstance(judge_passes, bool) or not isinstance(judge_passes, int) or judge_passes < 1:
        raise AggregateError("judge_passes must be a positive integer")
    if criterion_count is not None and (
        isinstance(criterion_count, bool)
        or not isinstance(criterion_count, int)
        or criterion_count < 1
    ):
        raise AggregateError("criterion_count must be a positive integer or None")
    # INVARIANT: absence of evaluated Cases is an execution failure, not Candidate score zero.
    if not rows:
        raise AggregateError("no DRACO rows were collected; the Candidate cannot be scored")
    expected_cases = _validate_selected_cases(selected_cases, len(rows))

    evaluations, decode_errors = _decode_evaluations(rows, expected_cases)
    case_rows = [
        [evaluation["case"]] if evaluation is not None else [] for evaluation in evaluations
    ]
    check_rows = [
        evaluation["checks"] if evaluation is not None else [] for evaluation in evaluations
    ]
    evidence_rows = [
        evaluation["evidence"] if evaluation is not None else [] for evaluation in evaluations
    ]
    _require_verifiable_mapping(case_rows, check_rows, evidence_rows, expected_cases)

    case_results = _aggregate_rows(
        rows,
        decode_errors,
        case_rows,
        check_rows,
        evidence_rows,
        expected_cases,
        rubrics,
        judge_passes,
        criterion_count,
    )
    scored = [
        case
        for case in case_results
        if isinstance((grade := case.get("grade")), Mapping)
        and isinstance(grade.get("score"), int | float)
        and not isinstance(grade.get("score"), bool)
    ]
    if len(scored) != len(case_results):
        return {
            "schema": CANDIDATE_RESULT_SCHEMA,
            "benchmark_id": benchmark_id,
            "benchmark_revision": benchmark_revision,
            "case_count": len(case_results),
            "score": None,
            "metrics": {},
            "cases": case_results,
            "failures": [],
        }

    return {
        "schema": CANDIDATE_RESULT_SCHEMA,
        "benchmark_id": benchmark_id,
        "benchmark_revision": benchmark_revision,
        "case_count": len(case_results),
        "score": _mean_grades(scored, "score"),
        "metrics": {
            "normalized_score_sd": _mean_grade_metrics(scored, "normalized_score_sd"),
            "pass_rate": _mean_grade_metrics(scored, "pass_rate"),
            "pass_rate_sd": _mean_grade_metrics(scored, "pass_rate_sd"),
            "accuracy": _mean_grade_metrics(scored, "accuracy"),
            "accuracy_pass_rate": _mean_grade_metrics(scored, "accuracy_pass_rate"),
            "axis_scores": _mean_grade_metric_maps(scored, "axis_scores"),
            "axis_pass_rates": _mean_grade_metric_maps(scored, "axis_pass_rates"),
            "coverage": _mean_grade_metrics(scored, "coverage"),
            "coverage_sd": _mean_grade_metrics(scored, "coverage_sd"),
            "coverage_target": COVERAGE_TARGET,
            "n_runs": max((_grade_metric(case, "n_runs") for case in scored), default=0),
            "verdicts_expected": _sum_grade_metrics(scored, "verdicts_expected"),
            "verdicts_accepted": _sum_grade_metrics(scored, "verdicts_accepted"),
            "verdicts_rejected": _sum_grade_metrics(scored, "verdicts_rejected"),
            "verdicts_invalid": _sum_grade_metrics(scored, "verdicts_invalid"),
            "verdicts_missing": _sum_grade_metrics(scored, "verdicts_missing"),
        },
        "cases": case_results,
        # Case-scoped failures live on their Case Result. Candidate-level failures are reserved
        # for failures that cannot be attributed to a selected Case.
        "failures": [],
    }


def _decode_evaluations(
    rows: Sequence[Any],
    expected_cases: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any] | None], list[str | None]]:
    evaluations: list[dict[str, Any] | None] = []
    errors: list[str | None] = []
    for raw, expected_case in zip(rows, expected_cases, strict=True):
        try:
            evaluation = decode_case_evaluation(raw, int(expected_case["id"]))
        except (TypeError, ValueError) as exc:
            evaluation = None
            errors.append(str(exc))
        else:
            errors.append(None)
        evaluations.append(evaluation)
    return evaluations, errors


def _aggregate_rows(
    raw_rows: Sequence[Any],
    decode_errors: Sequence[str | None],
    case_rows: Sequence[Sequence[Mapping[str, Any]]],
    check_rows: Sequence[Sequence[Mapping[str, Any]]],
    evidence_rows: Sequence[Sequence[Mapping[str, Any]]],
    expected_cases: Sequence[Mapping[str, Any]],
    rubrics: Mapping[int, Mapping[str, Any]],
    judge_passes: int,
    criterion_count: int | None,
) -> list[dict[str, Any]]:
    case_results: list[dict[str, Any]] = []
    for index, records in enumerate(evidence_rows):
        expected_case = expected_cases[index]
        case_records = case_rows[index]
        checks = check_rows[index]
        if not case_records:
            failure = _row_failure(
                raw_rows[index],
                index,
                expected_case,
                decode_errors[index],
            )
            case_results.append(_failed_selected_case_result(expected_case, failure))
            continue
        case_record = case_records[0]
        case_id = _as_int(case_record.get("case_id"))
        if case_id is None:  # pragma: no cover - sealed by _require_verifiable_mapping
            raise AssertionError("a scored DRACO row must carry its Engine-bound case_id")
        rubric = rubrics.get(case_id)
        if rubric is None:
            failure = {
                "stage": "grading",
                "code": "missing_case_rubric",
                "message": "the selected Case has no installed DRACO rubric",
                "retryable": None,
                "case_id": case_id,
                "metadata": {"row_index": index},
            }
            case_results.append(_ungraded_case_result(case_record, failure))
            continue
        verdicts = valid_verdicts(rubric, records, case_id)
        if not verdicts:
            failure = {
                "stage": "grading",
                "code": "no_valid_judge_verdict",
                "message": "no valid Judge verdict was produced for this Case",
                "retryable": None,
                "case_id": case_id,
                "metadata": {"row_index": index},
            }
            case_results.append(
                _incomplete_case_result(
                    case_record,
                    rubric,
                    checks,
                    records,
                    judge_passes,
                    criterion_count,
                    failure,
                )
            )
            continue
        case_results.append(
            _case_result(
                case_record,
                rubric,
                checks,
                records,
                verdicts,
                judge_passes,
                criterion_count,
            )
        )
    return case_results


def _row_failure(
    row: Any,
    index: int,
    expected_case: Mapping[str, Any],
    decode_error: str | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "row_index": index,
        **({"reason": " ".join(decode_error.split())[:200]} if decode_error else {}),
    }
    failure: dict[str, Any] = {
        "stage": "grading",
        "code": "invalid_case_evaluation",
        "message": "the Case produced no valid DRACO Case Evaluation",
        "retryable": None,
        "case_id": int(expected_case["id"]),
        "metadata": metadata,
    }
    error = row.get("error") if isinstance(row, Mapping) else None
    if not isinstance(error, Mapping):
        return failure
    metadata.clear()
    metadata["row_index"] = index
    selected = _bounded_error(error)
    failure.update(
        {
            "stage": "candidate",
            "code": selected.get("code", "case_execution_failed"),
            "message": selected.get("message", "Candidate Case execution failed"),
            "retryable": _retryable(error),
        }
    )
    if kind := selected.get("kind"):
        metadata["error_kind"] = kind
    return failure


def _bounded_error(error: Mapping[str, Any]) -> dict[str, str]:
    limits = {"kind": 80, "code": 80, "message": 200}
    return {
        field: " ".join(value.split())[:limit]
        for field, limit in limits.items()
        if isinstance((value := error.get(field)), str) and value.strip()
    }


def _retryable(error: Mapping[str, Any]) -> bool | None:
    if isinstance(value := error.get("retryable"), bool):
        return value
    if isinstance(permanent := error.get("permanent"), bool):
        return not permanent
    return None


def _case_result(
    case_record: Mapping[str, Any],
    rubric: Mapping[str, Any],
    check_records: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    verdicts: Sequence[Mapping[str, Any]],
    judge_passes: int,
    criterion_count: int | None,
) -> dict[str, Any]:
    case_id = int(case_record["case_id"])
    rubric_count = sum(1 for _ in flatten_criteria(rubric))
    if criterion_count is not None and criterion_count > rubric_count:
        raise AggregateError(
            f"criterion_count {criterion_count} exceeds Case {case_id} rubric size {rubric_count}"
        )
    criteria_expected = criterion_count if criterion_count is not None else rubric_count
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
    return {
        "case_id": case_id,
        "input": case_record["input"],
        "output": case_record["output"],
        "finish_reason": case_record["finish_reason"],
        "grade": {
            "method": "rubric",
            "score": score,
            "metrics": metrics,
            "checks": _checks(
                case_id,
                rubric,
                check_records,
                records,
                criteria_expected,
            ),
        },
        "failures": failures,
        "metadata": case_record.get("metadata", {}),
    }


def _incomplete_case_result(
    case_record: Mapping[str, Any],
    rubric: Mapping[str, Any],
    check_records: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    judge_passes: int,
    criterion_count: int | None,
    failure: Mapping[str, Any],
) -> dict[str, Any]:
    """Retain auditable grading material when no Judge Evidence was scoreable."""

    case_id = int(case_record["case_id"])
    rubric_count = sum(1 for _ in flatten_criteria(rubric))
    if criterion_count is not None and criterion_count > rubric_count:
        raise AggregateError(
            f"criterion_count {criterion_count} exceeds Case {case_id} rubric size {rubric_count}"
        )
    criteria_expected = criterion_count if criterion_count is not None else rubric_count
    verdicts_expected = criteria_expected * judge_passes
    return {
        "case_id": case_id,
        "input": case_record["input"],
        "output": case_record["output"],
        "finish_reason": case_record["finish_reason"],
        "grade": {
            "method": "rubric",
            "score": None,
            "metrics": {
                "normalized_score_sd": 0.0,
                "pass_rate": 0.0,
                "pass_rate_sd": 0.0,
                "accuracy": 0.0,
                "accuracy_pass_rate": 0.0,
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
            },
            "checks": _checks(
                case_id,
                rubric,
                check_records,
                evidence,
                criteria_expected,
            ),
        },
        "failures": [dict(failure)],
        "metadata": case_record.get("metadata", {}),
    }


def _failed_selected_case_result(
    selected_case: Mapping[str, Any], failure: Mapping[str, Any]
) -> dict[str, Any]:
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


def _ungraded_case_result(
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
        if record is None or _as_int(record.get("case_id")) != case_id:
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


def _require_verifiable_mapping(
    cases: Sequence[Sequence[Mapping[str, Any]]],
    checks: Sequence[Sequence[Mapping[str, Any]]],
    evidence_rows: Sequence[Sequence[Mapping[str, Any]]],
    expected_cases: Sequence[Mapping[str, Any]],
) -> None:
    """Require one unique Engine-bound Case identity for every scoreable row."""

    claimed: dict[int, int] = {}
    for index, (case_records, check_records, verdicts) in enumerate(
        zip(cases, checks, evidence_rows, strict=True)
    ):
        if not case_records and not verdicts:
            continue
        if len(case_records) != 1:
            raise AggregateError(
                f"row {index} must carry exactly one Engine-bound Case record; "
                f"found {len(case_records)}"
            )
        ids = [
            _as_int(record.get("case_id")) for record in (*case_records, *check_records, *verdicts)
        ]
        if any(case_id is None for case_id in ids):
            raise AggregateError(f"row {index} has a verdict without an Engine-bound case_id")
        unique = {case_id for case_id in ids if case_id is not None}
        if len(unique) != 1:
            raise AggregateError(f"row {index} carries multiple case_id values {sorted(unique)}")
        case_id = unique.pop()
        previous = claimed.get(case_id)
        if previous is not None:
            raise AggregateError(
                f"duplicate case_id {case_id} appears in rows {previous} and {index}"
            )
        expected_id = int(expected_cases[index]["id"])
        if case_id != expected_id:
            raise AggregateError(
                f"row {index} claims case_id {case_id}, but the selected Case is {expected_id}"
            )
        claimed[case_id] = index


def _validate_selected_cases(
    selected_cases: Sequence[Mapping[str, Any]], row_count: int
) -> list[Mapping[str, Any]]:
    if len(selected_cases) < row_count:
        raise AggregateError(
            f"selected Case sequence has {len(selected_cases)} entries for {row_count} rows"
        )
    expected = list(selected_cases[:row_count])
    ids: set[int] = set()
    for index, case in enumerate(expected):
        case_id = _as_int(case.get("id")) if isinstance(case, Mapping) else None
        input_value = case.get("input") if isinstance(case, Mapping) else None
        if case_id is None or case_id < 1 or not isinstance(input_value, str) or not input_value:
            raise AggregateError(f"selected Case {index} must carry a positive id and input text")
        if case_id in ids:
            raise AggregateError(f"selected Case sequence repeats case_id {case_id}")
        ids.add(case_id)
    return expected


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _grade(case: Mapping[str, Any]) -> Mapping[str, Any]:
    grade = case.get("grade")
    if not isinstance(grade, Mapping):  # pragma: no cover - selected by caller
        raise AssertionError("scored Case must carry a Case Grade")
    return grade


def _grade_metric(case: Mapping[str, Any], key: str) -> Any:
    metrics = _grade(case).get("metrics")
    if not isinstance(metrics, Mapping):  # pragma: no cover - constructed locally
        raise AssertionError("Case Grade must carry metrics")
    return metrics[key]


def _mean_grades(cases: Sequence[Mapping[str, Any]], key: str) -> float:
    return round(sum(float(_grade(case)[key]) for case in cases) / len(cases), 4)


def _mean_grade_metrics(cases: Sequence[Mapping[str, Any]], key: str) -> float:
    return round(sum(float(_grade_metric(case, key)) for case in cases) / len(cases), 4)


def _sum_grade_metrics(cases: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(int(_grade_metric(case, key)) for case in cases)


def _mean_grade_metric_maps(cases: Sequence[Mapping[str, Any]], key: str) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for case in cases:
        metric = _grade_metric(case, key)
        if not isinstance(metric, Mapping):  # pragma: no cover - constructed locally
            raise AssertionError(f"Case Grade metric {key!r} must be an object")
        for name, value in metric.items():
            values.setdefault(str(name), []).append(float(value))
    return {name: round(sum(items) / len(items), 4) for name, items in sorted(values.items())}


def load_rubrics(directory: Path) -> dict[int, dict[str, Any]]:
    """Load ``<directory>/<case_id>.json`` for every rubric on disk.

    The rubrics are PRIVATE: they live only in the image and are read here, never returned to a
    client. Only the case id crosses the wire.

    INVARIANT: an absent or empty directory RAISES. Returning ``{}`` makes every case an
    "unknown case_id" failure, which reaches the client as a terminated-succeeded run carrying a
    plausible zero score — observed live, from a path that pointed into the image while the
    runner ran outside it. A misconfigured path must be loud.
    """
    rubrics: dict[int, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        case_id = _as_int(path.stem)
        if case_id is not None:
            rubrics[case_id] = json.loads(path.read_text(encoding="utf-8"))
    if not rubrics:
        raise AggregateError(
            f"no rubrics under {str(directory)!r}; the installed DRACO assets are incomplete"
        )
    return rubrics
