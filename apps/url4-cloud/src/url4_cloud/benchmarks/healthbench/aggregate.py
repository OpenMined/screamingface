"""Reduce collected HealthBench Case evaluations into one challenge result.

Think of this as the exam office totalling a stack of graded papers into one
final grade. It receives one row per Case (the graded paper), scores each, and
returns the exam score: the unclipped mean of the Case scores.

INVARIANT — all-or-nothing: if ANY Case can't be scored, the exam score is
``None``. Every broken Case still shows up in ``cases`` as ``status: "failed"``
with a reason; nothing is silently skipped.

Why so strict? Two ways a lenient reducer would quietly CHEAT in the
submitter's favor:

1. **Dropping a failed Case inflates the mean.** These are the 157 *hardest*
   Cases — most score low. Example: scores ``[0.9, 0.1, <failed>]``. Averaging
   the survivors gives 0.50; the honest three-Case run would likely land near
   0.35. The failure deleted a hard row and the score went UP (review finding
   B1 against DRACO's reducer).
2. **Defaulting a missing verdict erases a penalty.** A rubric penalty item
   (say -3, "invents a dosage") only subtracts when the judge says "hit". If
   the judge call failed and we defaulted to "not hit", the -3 vanishes and the
   Case scores higher than it should.

Both are excluded structurally: a Case is scored only when every rubric item
has a valid verdict (no defaults), and the mean is computed only when every
selected Case scored (no drops). Broken input at any level — unreadable rubric
asset, missing or error-collected row, invalid judge reply, partial verdict
set — becomes a visible failed Case, never a shrug.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from url4_cloud.benchmarks.aggregation import (
    CandidateScore,
    SelectedCase,
    collected_provider_refusal,
    failed_case_result,
    finalize_candidate_result,
    public_error,
    refused_case_result,
    scored_case_result,
)
from url4_cloud.benchmarks.contract import CaseResult
from url4_cloud.benchmarks.healthbench.case_evaluation import CASE_EVALUATION_SCHEMA
from url4_cloud.benchmarks.healthbench.scoring import (
    case_score,
    sample_stdev,
    unclipped_mean,
    verdict_coverage,
)


class AggregateError(ValueError):
    """The reducer's input is unusable — raised before any scoring."""


def load_rubric_points(root: Path, case_id: int) -> list[int] | None:
    """Read one Case's private points list; ``None`` when the asset is unusable."""

    path = root / "rubrics" / f"{case_id}.json"
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _points_from(decoded)


def _points_from(decoded: object) -> list[int] | None:
    items = decoded.get("items") if isinstance(decoded, Mapping) else None
    if not isinstance(items, list) or not items:
        return None
    points: list[int] = []
    for index, item in enumerate(items, start=1):
        value = item.get("points") if isinstance(item, Mapping) else None
        usable = (
            not isinstance(value, bool)
            and isinstance(value, int)
            and isinstance(item, Mapping)
            and item.get("rubric_id") == index
        )
        if not usable:
            return None
        assert isinstance(value, int)
        points.append(value)
    return points


def _selected_cases(root: Path, case_ids: tuple[int, ...]) -> list[SelectedCase]:
    try:
        decoded = json.loads((root / "cases.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AggregateError(f"HealthBench cases are unavailable: {exc}") from None
    if not isinstance(decoded, list):
        raise AggregateError("HealthBench cases must be a JSON array")
    by_id = {
        row.get("id"): row
        for row in decoded
        if isinstance(row, Mapping)
        and isinstance(row.get("id"), int)
        and not isinstance(row.get("id"), bool)
    }
    selected: list[SelectedCase] = []
    for case_id in case_ids:
        row = by_id.get(case_id)
        input_value = row.get("input") if isinstance(row, Mapping) else None
        if not isinstance(input_value, str) or not input_value.strip():
            raise AggregateError(f"HealthBench Case {case_id} has no public input")
        selected.append(SelectedCase(case_id=case_id, input=input_value, metadata={}))
    return selected


def aggregate(
    raw_rows: str,
    root: Path,
    *,
    benchmark_id: str,
    benchmark_revision: str,
    case_ids: tuple[int, ...],
) -> dict[str, Any]:
    """Score every selected Case, then the exam — unclipped mean (see scoring.py).

    Walks ``case_ids`` (the selection is authoritative — rows that showed up but
    weren't selected don't count, selected Cases with no row fail visibly), scores
    each via ``_case_result``, and only if EVERY Case scored computes the mean —
    the all-or-nothing rule from the module docstring. The metrics block reports
    how healthy the run was (coverage, invalid judge replies, failed Cases) so a
    ``score: None`` is diagnosable from the result alone.

    Reference counterpart: the metric aggregation in ``HealthBenchEval``
    (https://github.com/openai/simple-evals/blob/main/healthbench_eval.py) —
    deliberately DIVERGING on the clip (unclipped mean, see module docstring)
    and on spread (sample stdev, see ``scoring.sample_stdev``).
    """

    selected_cases = _selected_cases(root, case_ids)
    by_case, errors_by_case = _index_rows(_decode_rows(raw_rows), case_ids)
    case_results: list[CaseResult] = []
    for selected in selected_cases:
        case_id = int(selected.case_id)
        points = load_rubric_points(root, case_id)
        result, _, _, _, _ = _case_result(
            selected, by_case.get(case_id), points, errors_by_case.get(case_id)
        )
        case_results.append(result)
    return finalize_candidate_result(
        benchmark_id=benchmark_id,
        benchmark_revision=benchmark_revision,
        selected_cases=selected_cases,
        cases=case_results,
        scorer=_healthbench_score,
    ).as_payload()


def _healthbench_score(cases: Sequence[CaseResult]) -> CandidateScore:
    """Apply HealthBench's unclipped penalty-bearing reduction to complete Cases."""

    grades = [case.grade for case in cases]
    if any(grade is None or grade.score is None for grade in grades):  # pragma: no cover
        raise AssertionError("HealthBench scorer requires complete graded Cases")
    typed_grades = [grade for grade in grades if grade is not None and grade.score is not None]
    scores = [float(grade.score) for grade in typed_grades if grade.score is not None]
    judged_items = sum(int(grade.metrics["judged"]) for grade in typed_grades)
    total_items = sum(int(grade.metrics["expected"]) for grade in typed_grades)
    invalid_replies = sum(int(grade.metrics["invalid_replies"]) for grade in typed_grades)
    met_items = sum(1 for grade in typed_grades for check in grade.checks if check.outcome == "MET")
    coverage = round(verdict_coverage(judged_items, total_items), 4)
    mean = unclipped_mean(scores)
    if mean is None:  # pragma: no cover - a Benchmark always selects at least one Case
        raise AssertionError("HealthBench scorer requires at least one Case")
    return CandidateScore(
        score=round(mean, 4),
        metrics={
            "pass_rate": round(met_items / judged_items, 4) if judged_items else 0.0,
            "coverage": coverage,
            "scored_cases": len(scores),
            "failed_cases": 0,
            "score_sd": round(sample_stdev(scores), 4),
            "verdict_coverage": coverage,
            "judge_invalid_replies": invalid_replies,
        },
    )


def _case_result(
    selected_case: SelectedCase,
    row: Mapping[str, Any] | None,
    points: list[int] | None,
    orphan_errors: list[dict[str, Any]] | None = None,
) -> tuple[CaseResult, float | None, int, int, int]:
    """Score one selected Case; every unusable state becomes a VISIBLE failed result.

    A decision ladder, most-broken first — each rung becomes a Failure whose
    ``code`` makes a ``None`` exam score traceable per Case:

        no rubric asset      → "missing_rubric_asset"
        no row for this Case → "missing_case_row"
        row is an error row  → "case_error" (error attached in metadata)
        verdicts incomplete  → "incomplete_verdicts" (judged/expected counts)
        complete, no + item  → "no_positive_points" (a baked-asset defect —
                               prepare guarantees one positive item per Case)
        scored, no envelope  → "invalid_case_evaluation" (fully judged but the
                               hoisted case record carries no usable output —
                               a scored result REQUIRES one, contract rule)
        everything valid     → grade with the Case score, no failures

    Returns ``(case_result, score_or_None, judged_count, met_count,
    invalid_reply_count)``.
    """

    case_id = int(selected_case.case_id)
    if points is None:
        failure = _failure(case_id, "grading", "missing_rubric_asset")
        outcome = _failed_result(selected_case, row, [], failure), None, 0, 0, 0
    elif row is None:
        # WHY the collected_errors attachment: an on_error=collect row loses its
        # Case identity, so a mid-chain error surfaces HERE as a missing row —
        # without the orphan payloads the report would name the symptom but hide
        # the cause (exactly what happened in the first live smoke run).
        outcome = _missing_row_outcome(selected_case, orphan_errors)
    elif "error" in row:
        failure = _failure(case_id, "candidate", "case_error", error=row["error"])
        outcome = _failed_result(selected_case, row, [], failure), None, 0, 0, 0
    else:
        verdicts, invalid = _verdicts(row)
        checks = _checks(row, points)
        score = (
            case_score(points, verdicts) if len(verdicts) == len(points) and not invalid else None
        )
        if score is None:
            complete = len(verdicts) == len(points) and not invalid
            failure = _failure(
                case_id,
                "grading",
                # WHY: a complete-but-unscorable Case means the baked asset lost its
                # positive-points item (prepare guarantees one) — name it distinctly.
                "no_positive_points" if complete else "incomplete_verdicts",
                judged=len(verdicts),
                expected=len(points),
            )
            outcome = (
                _failed_result(selected_case, row, checks, failure),
                None,
                len(verdicts),
                sum(verdicts.values()),
                invalid,
            )
        elif _candidate_fields(row)["output"] is None:
            # WHY: the contract forbids a scored Case without an output — a
            # fully-judged row whose hoisted case envelope is missing or
            # malformed must fail VISIBLY here, not trip the CaseResult
            # validator and turn the whole Candidate run into
            # benchmark_unavailable (one bad row destroying a paid run).
            failure = _failure(case_id, "candidate", "invalid_case_evaluation")
            outcome = (
                _failed_result(selected_case, row, checks, failure),
                None,
                len(verdicts),
                sum(verdicts.values()),
                invalid,
            )
        else:
            fields = _candidate_fields(row)
            scored = scored_case_result(
                selected_case=selected_case,
                output=fields["output"],
                finish_reason=fields["finish_reason"],
                grade={
                    "method": "rubric",
                    "score": round(score, 4),
                    "metrics": {
                        "judged": len(verdicts),
                        "expected": len(points),
                        "invalid_replies": invalid,
                    },
                    "checks": checks,
                },
                metadata=fields["metadata"],
            )
            outcome = scored, score, len(verdicts), sum(verdicts.values()), invalid
    return outcome


def _missing_row_outcome(
    selected_case: SelectedCase, orphan_errors: list[dict[str, Any]] | None
) -> tuple[CaseResult, None, int, int, int]:
    refusal = next(
        (
            value
            for error in orphan_errors or []
            if (value := collected_provider_refusal(error)) is not None
        ),
        None,
    )
    if refusal is not None:
        refused = refused_case_result(
            selected_case=selected_case,
            refusal=refusal.text,
            finish_reason=refusal.finish_reason,
        )
        return refused, None, 0, 0, 0
    case_id = int(selected_case.case_id)
    failure = _failure(
        case_id,
        "candidate",
        "missing_case_row",
        **({"collected_errors": orphan_errors[:3]} if orphan_errors else {}),
    )
    return _failed_result(selected_case, None, [], failure), None, 0, 0, 0


def _candidate_fields(row: Mapping[str, Any] | None) -> dict[str, Any]:
    """Pull input/output/finish_reason/metadata off the hoisted Case record."""

    case = row.get("case") if isinstance(row, Mapping) else None
    if not isinstance(case, Mapping):
        return {"output": None, "finish_reason": None, "metadata": {}}
    metadata = case.get("metadata")
    output = case.get("output")
    finish_reason = case.get("finish_reason")
    return {
        "output": output if isinstance(output, str) else None,
        "finish_reason": finish_reason if isinstance(finish_reason, str) else None,
        "metadata": dict(metadata) if isinstance(metadata, Mapping) else {},
    }


def _failed_result(
    selected_case: SelectedCase,
    row: Mapping[str, Any] | None,
    checks: list[dict[str, Any]],
    failure: dict[str, Any],
) -> CaseResult:
    fields = _candidate_fields(row)
    grade = (
        None
        if not checks
        else {
            # WHY a grade with score None instead of dropping the checks: the
            # judge evidence for an incompletely-judged Case is audit material
            # (module INVARIANT) and the grade's checks list is the contract's
            # slot for it.
            "method": "rubric",
            "score": None,
            "metrics": {},
            "checks": checks,
        }
    )
    return failed_case_result(
        selected_case=selected_case,
        failures=[failure],
        output=fields["output"],
        finish_reason=fields["finish_reason"],
        grade=grade,
        metadata=fields["metadata"],
    )


def _checks(row: Mapping[str, Any], points: list[int]) -> list[dict[str, Any]]:
    """Project rubric evaluations into the SDK's check/evidence rows."""

    evaluations = row.get("rubric_evaluations")
    if not isinstance(evaluations, list):
        return []
    checks: dict[int, dict[str, Any]] = {}
    for evaluation in evaluations:
        if not isinstance(evaluation, Mapping):
            continue
        rubric = evaluation.get("rubric")
        evidence = evaluation.get("evidence")
        rubric_id = evaluation.get("rubric_id")
        if (
            not isinstance(rubric, Mapping)
            or not isinstance(evidence, Mapping)
            or isinstance(rubric_id, bool)
            or not isinstance(rubric_id, int)
        ):
            continue
        check: dict[str, Any] = {
            "type": "rubric_item",
            "id": str(rubric_id),
            "label": str(rubric.get("rubric_item", "")),
            "evidence": [_evidence(evidence)],
        }
        # Check-level verdict in the report schema's vocabulary — the judge decides
        # it. Without a top-level outcome the SDK renders the check as unjudged
        # (ifeval precedent), so it is emitted whenever the judge reply was valid;
        # an invalid reply leaves the check outcome-less on purpose.
        if evidence.get("valid") is True:
            check["outcome"] = "MET" if evidence.get("criteria_met") is True else "UNMET"
        # One check per rubric_id, last entry wins — the same dict-assignment
        # dedup as _verdicts, so a duplicate judge entry (retry noise) never
        # becomes a second check and met can never exceed judged.
        checks[rubric_id] = {
            **check,
            "metadata": (
                {"points": points[rubric_id - 1]} if 1 <= rubric_id <= len(points) else {}
            ),
        }
    return list(checks.values())


def _evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    valid = record.get("valid") is True
    value: dict[str, Any] = {
        # One judge pass per rubric item (the reference grades each item once),
        # so the sequence is always 1.
        "sequence": 1,
        "producer": {
            "type": str(record.get("producer_type", "model")),
            # Even a malformed Judge reply has a known Benchmark-owned producer.
            "id": str(record.get("producer_id") or "healthbench/judge"),
        },
        "valid": valid,
        "raw_output": str(record.get("raw_output", "")),
        "metadata": {},
    }
    if valid:
        value["outcome"] = "MET" if record.get("criteria_met") is True else "UNMET"
        value["explanation"] = str(record.get("explanation", ""))
    else:
        value["metadata"] = {"rejection_reason": str(record.get("reason", "invalid"))}
    return value


def _failure(case_id: int, stage: str, code: str, **metadata: Any) -> dict[str, Any]:
    public_metadata = _failure_metadata(metadata)
    message = _FAILURE_MESSAGES[code]
    retryable: bool | None = None
    if source_error := _source_error(metadata):
        diagnostic = public_error(
            source_error,
            default_code=code,
            default_message=message,
        )
        message = diagnostic.message
        retryable = diagnostic.retryable
        public_metadata["source_error"] = {
            "kind": diagnostic.kind,
            "code": diagnostic.code,
            "message": diagnostic.message,
            "retryable": diagnostic.retryable,
        }
    return {
        "stage": stage,
        "code": code,
        "message": message,
        "retryable": retryable,
        "case_id": case_id,
        "metadata": public_metadata,
    }


def _failure_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    public = {
        key: value
        for key, value in metadata.items()
        if key in {"judged", "expected", "row_index"}
        and isinstance(value, int)
        and not isinstance(value, bool)
    }
    return public


def _source_error(metadata: Mapping[str, Any]) -> Mapping[str, Any] | None:
    error = metadata.get("error")
    if isinstance(error, Mapping):
        return error
    collected = metadata.get("collected_errors")
    rows = collected[:3] if isinstance(collected, list) else []
    return next(
        (
            source
            for row in rows
            if isinstance(row, Mapping) and isinstance((source := row.get("error")), Mapping)
        ),
        None,
    )


_FAILURE_MESSAGES = {
    "missing_rubric_asset": "the baked rubric asset for this Case is missing or invalid",
    "missing_case_row": "no evaluation row for this Case reached the aggregate",
    "case_error": "the Case pipeline collected an error instead of an evaluation",
    "incomplete_verdicts": "not every rubric item received a valid judge verdict",
    "no_positive_points": "no judged rubric item carries positive points (baked-asset defect)",
    "invalid_case_evaluation": "the evaluation row lacked a usable candidate envelope",
}


def _decode_rows(raw: str) -> list[Any]:
    try:
        decoded = json.loads(raw or "")
    except ValueError as exc:
        raise AggregateError(f"HealthBench rows are not JSON: {exc}") from None
    if not isinstance(decoded, list):
        raise AggregateError("HealthBench rows must be a JSON array")
    return decoded


def _index_rows(
    rows: list[Any], case_ids: tuple[int, ...]
) -> tuple[dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    """Split rows into per-Case evaluations and identity-less orphan error rows.

    An ``on_error=collect`` row loses its Case identity, so it cannot be indexed;
    it is RETAINED as an orphan and attached to whichever selected Case ends up
    with no row (the missing_case_row failure) — the cause must never be dropped.
    """

    indexed: dict[int, dict[str, Any]] = {}
    errors_by_case: dict[int, list[dict[str, Any]]] = {}
    for index, entry in enumerate(rows):
        expected_case_id = case_ids[index] if index < len(case_ids) else None
        row, parse_error = _row_value(entry)
        if parse_error is not None:
            _attach_collected_error(errors_by_case, expected_case_id, parse_error)
            continue
        if row is None:
            continue
        if "error" in row and "case_id" not in row:
            _attach_collected_error(errors_by_case, expected_case_id, dict(row))
            continue
        if row.get("schema") == CASE_EVALUATION_SCHEMA:
            case_id = row.get("case_id")
            if isinstance(case_id, int) and not isinstance(case_id, bool):
                indexed[case_id] = dict(row)
    return indexed, errors_by_case


def _row_value(entry: object) -> tuple[Mapping[str, Any] | None, dict[str, Any] | None]:
    try:
        row = json.loads(entry) if isinstance(entry, str) else entry
    except ValueError:
        return None, {"error": {"kind": "InvalidCollectedRow"}}
    return (row, None) if isinstance(row, Mapping) else (None, None)


def _attach_collected_error(
    target: dict[int, list[dict[str, Any]]],
    case_id: int | None,
    error: dict[str, Any],
) -> None:
    if case_id is not None:
        target.setdefault(case_id, []).append(error)


def _verdicts(row: Mapping[str, Any]) -> tuple[dict[int, bool], int]:
    verdicts: dict[int, bool] = {}
    invalid = 0
    evaluations = row.get("rubric_evaluations")
    if not isinstance(evaluations, list):
        return verdicts, invalid
    for evaluation in evaluations:
        if not isinstance(evaluation, Mapping):
            invalid += 1
            continue
        evidence = evaluation.get("evidence")
        if not isinstance(evidence, Mapping) or evidence.get("valid") is not True:
            invalid += 1
            continue
        rubric_id = evidence.get("rubric_id")
        criteria_met = evidence.get("criteria_met")
        if (
            isinstance(rubric_id, int)
            and not isinstance(rubric_id, bool)
            and (criteria_met is True or criteria_met is False)
        ):
            verdicts[rubric_id] = criteria_met
        else:
            invalid += 1
    return verdicts, invalid


__all__ = [
    "AggregateError",
    "CaseResult",
    "aggregate",
    "load_rubric_points",
]
