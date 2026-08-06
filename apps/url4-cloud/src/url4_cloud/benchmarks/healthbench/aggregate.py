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
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict

from url4_cloud.benchmarks.contract import CANDIDATE_RESULT_SCHEMA
from url4_cloud.benchmarks.healthbench.case_evaluation import CASE_EVALUATION_SCHEMA
from url4_cloud.benchmarks.healthbench.scoring import (
    case_score,
    sample_stdev,
    unclipped_mean,
    verdict_coverage,
)


class AggregateError(ValueError):
    """The reducer's input is unusable — raised before any scoring."""


class CaseResult(TypedDict):
    """One selected Case in the SDK's Case Result wire shape.

    The SDK decoder requires EXACTLY these keys (see screamingface
    ``_evaluation/results.py``); draco set the projection precedent. A scored
    Case carries a ``grade`` (method/score/metrics/checks) and empty
    ``failures``; a failed Case carries ``grade: None`` plus one Failure row
    whose ``code`` names the rung of the decision ladder.
    """

    case_id: int
    input: str | None
    output: str | None
    finish_reason: str | None
    grade: dict[str, Any] | None
    failures: list[dict[str, Any]]
    metadata: dict[str, Any]


class Metrics(TypedDict, total=False):
    """Run-health block for a SCORED exam.

    INVARIANT (SDK decoder rules, pinned by test_healthbench_sdk_contract):
    values are NUMBERS only, and an unscored Candidate must carry EMPTY metrics
    — so on ``score: None`` this block is ``{}`` and diagnosis lives in each
    Case's ``failures`` instead. The scoring identity ("unclipped-mean-v1") is
    carried by the revision hash and the benchmark description, never here.
    """

    scored_cases: int
    failed_cases: int
    score_sd: float
    verdict_coverage: float
    judge_invalid_replies: int


class CandidateResult(TypedDict):
    """The wire shape of one exam result (``CANDIDATE_RESULT_SCHEMA``).

    A TypedDict, not Pydantic: this side only PRODUCES the payload (inputs are
    validated upstream), so the win is pyright-checked keys at zero runtime cost —
    ``json.dumps`` serializes it unchanged.
    """

    schema: str
    benchmark_id: str
    benchmark_revision: str
    case_count: int
    score: float | None
    metrics: Metrics
    cases: list[CaseResult]
    failures: list[dict[str, Any]]


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


def aggregate(
    raw_rows: str,
    root: Path,
    *,
    benchmark_id: str,
    benchmark_revision: str,
    case_ids: tuple[int, ...],
) -> CandidateResult:
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

    by_case, orphan_errors = _index_rows(_decode_rows(raw_rows))
    case_results: list[CaseResult] = []
    scores: list[float] = []
    judged_items = 0
    total_items = 0
    invalid_replies = 0
    for case_id in case_ids:
        points = load_rubric_points(root, case_id)
        total_items += len(points) if points is not None else 0
        result, score, judged, invalid = _case_result(
            case_id, by_case.get(case_id), points, orphan_errors
        )
        case_results.append(result)
        judged_items += judged
        invalid_replies += invalid
        if score is not None:
            scores.append(score)
    scored_all = len(scores) == len(case_ids)
    mean = unclipped_mean(scores) if scored_all else None
    return {
        "schema": CANDIDATE_RESULT_SCHEMA,
        "benchmark_id": benchmark_id,
        "benchmark_revision": benchmark_revision,
        "case_count": len(case_results),
        # WHY: None whenever ANY selected Case failed — a partial mean over surviving
        # Cases would silently drop exactly the hardest rows (B1).
        "score": round(mean, 4) if mean is not None else None,
        # SDK rule: an unscored Candidate must carry EMPTY metrics — when any Case
        # failed, diagnosis lives in that Case's failures rows, not up here.
        "metrics": (
            {}
            if mean is None
            else {
                "scored_cases": len(scores),
                "failed_cases": len(case_ids) - len(scores),
                "score_sd": round(sample_stdev(scores), 4),
                "verdict_coverage": round(verdict_coverage(judged_items, total_items), 4),
                "judge_invalid_replies": invalid_replies,
            }
        ),
        "cases": case_results,
        # Case-scoped failures live on their Case result rows above. This top-level
        # list is the contract's slot for failures attributable to NO selected Case
        # (draco precedent) — healthbench routes every failure to a Case, so it is
        # always empty, but the SDK requires the key.
        "failures": [],
    }


def _case_result(
    case_id: int,
    row: Mapping[str, Any] | None,
    points: list[int] | None,
    orphan_errors: list[dict[str, Any]] | None = None,
) -> tuple[CaseResult, float | None, int, int]:
    """Score one selected Case; every unusable state becomes a VISIBLE failed result.

    A decision ladder, most-broken first — each rung becomes a Failure whose
    ``code`` makes a ``None`` exam score traceable per Case:

        no rubric asset      → "missing_rubric_asset"
        no row for this Case → "missing_case_row"
        row is an error row  → "case_error" (error attached in metadata)
        verdicts incomplete  → "incomplete_verdicts" (judged/expected counts)
        complete, no + item  → "no_positive_points" (a baked-asset defect —
                               prepare guarantees one positive item per Case)
        everything valid     → grade with the Case score, no failures

    Returns ``(case_result, score_or_None, judged_count, invalid_reply_count)``.
    """

    if points is None:
        failure = _failure(case_id, "grading", "missing_rubric_asset")
        outcome = _failed_result(case_id, row, [], failure), None, 0, 0
    elif row is None:
        # WHY the collected_errors attachment: an on_error=collect row loses its
        # Case identity, so a mid-chain error surfaces HERE as a missing row —
        # without the orphan payloads the report would name the symptom but hide
        # the cause (exactly what happened in the first live smoke run).
        failure = _failure(
            case_id,
            "candidate",
            "missing_case_row",
            **({"collected_errors": orphan_errors[:3]} if orphan_errors else {}),
        )
        outcome = _failed_result(case_id, None, [], failure), None, 0, 0
    elif "error" in row:
        failure = _failure(case_id, "candidate", "case_error", error=row["error"])
        outcome = _failed_result(case_id, row, [], failure), None, 0, 0
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
            outcome = _failed_result(case_id, row, checks, failure), None, len(verdicts), invalid
        else:
            scored: CaseResult = {
                "case_id": case_id,
                **_candidate_fields(row),
                "grade": {
                    "method": "rubric",
                    "score": round(score, 4),
                    "metrics": {
                        "judged": len(verdicts),
                        "expected": len(points),
                        "invalid_replies": invalid,
                    },
                    "checks": checks,
                },
                "failures": [],
            }
            outcome = scored, score, len(verdicts), invalid
    return outcome


def _candidate_fields(row: Mapping[str, Any] | None) -> dict[str, Any]:
    """Pull input/output/finish_reason/metadata off the hoisted Case record."""

    case = row.get("case") if isinstance(row, Mapping) else None
    if not isinstance(case, Mapping):
        return {"input": None, "output": None, "finish_reason": None, "metadata": {}}
    metadata = case.get("metadata")
    return {
        "input": case.get("input"),
        "output": case.get("output"),
        "finish_reason": case.get("finish_reason"),
        "metadata": dict(metadata) if isinstance(metadata, Mapping) else {},
    }


def _failed_result(
    case_id: int,
    row: Mapping[str, Any] | None,
    checks: list[dict[str, Any]],
    failure: dict[str, Any],
) -> CaseResult:
    return {
        "case_id": case_id,
        **_candidate_fields(row),
        "grade": (
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
        ),
        "failures": [failure],
    }


def _checks(row: Mapping[str, Any], points: list[int]) -> list[dict[str, Any]]:
    """Project rubric evaluations into the SDK's check/evidence rows."""

    evaluations = row.get("rubric_evaluations")
    if not isinstance(evaluations, list):
        return []
    checks: list[dict[str, Any]] = []
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
        checks.append(
            {
                "type": "rubric_item",
                "id": str(rubric_id),
                "label": str(rubric.get("rubric_item", "")),
                "evidence": [_evidence(evidence)],
                "metadata": (
                    {"points": points[rubric_id - 1]} if 1 <= rubric_id <= len(points) else {}
                ),
            }
        )
    return checks


def _evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    valid = record.get("valid") is True
    value: dict[str, Any] = {
        # One judge pass per rubric item (the reference grades each item once),
        # so the sequence is always 1.
        "sequence": 1,
        "producer": {
            "type": str(record.get("producer_type", "model")),
            "id": str(record.get("producer_id", "")),
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
    return {
        "stage": stage,
        "code": code,
        "message": _FAILURE_MESSAGES[code],
        "retryable": None,
        "case_id": case_id,
        "metadata": metadata,
    }


_FAILURE_MESSAGES = {
    "missing_rubric_asset": "the baked rubric asset for this Case is missing or invalid",
    "missing_case_row": "no evaluation row for this Case reached the aggregate",
    "case_error": "the Case pipeline collected an error instead of an evaluation",
    "incomplete_verdicts": "not every rubric item received a valid judge verdict",
    "no_positive_points": "no judged rubric item carries positive points (baked-asset defect)",
}


def _decode_rows(raw: str) -> list[Any]:
    try:
        decoded = json.loads(raw or "")
    except ValueError as exc:
        raise AggregateError(f"HealthBench rows are not JSON: {exc}") from None
    if not isinstance(decoded, list) or not decoded:
        raise AggregateError("HealthBench rows must be a non-empty JSON array")
    return decoded


def _index_rows(rows: list[Any]) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    """Split rows into per-Case evaluations and identity-less orphan error rows.

    An ``on_error=collect`` row loses its Case identity, so it cannot be indexed;
    it is RETAINED as an orphan and attached to whichever selected Case ends up
    with no row (the missing_case_row failure) — the cause must never be dropped.
    """

    indexed: dict[int, dict[str, Any]] = {}
    orphans: list[dict[str, Any]] = []
    for entry in rows:
        try:
            row = json.loads(entry) if isinstance(entry, str) else entry
        except ValueError:
            orphans.append({"error": "unparseable row", "row_head": str(entry)[:200]})
            continue
        if not isinstance(row, Mapping):
            continue
        if "error" in row and "case_id" not in row:
            orphans.append(dict(row))
            continue
        if row.get("schema") == CASE_EVALUATION_SCHEMA:
            case_id = row.get("case_id")
            if isinstance(case_id, int) and not isinstance(case_id, bool):
                indexed[case_id] = dict(row)
    return indexed, orphans


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
    "CandidateResult",
    "CaseResult",
    "Metrics",
    "aggregate",
    "load_rubric_points",
]
