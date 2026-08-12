"""The IFEval cross-row reducer — check records in, `CandidateResult` out.

FEATURE: one url4 expression per Candidate ends in a cross-row reduce that turns every
case's deterministic check into one scored result.
STORY: as a researcher, the number I publish is the IFEval paper's prompt-level strict
accuracy (arXiv:2311.07911).

INVARIANT: `case_count` is EXACT (one entry per selected Case) and every scored Case has a
real verifier record. A missing record is an operational failure rather than an incorrect
answer: the Case is retained with its failure record and the complete Candidate fails closed
with `score: None` and empty metrics. No accuracy is published over a surviving subset.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from url4_cloud.benchmarks.aggregation import (
    CandidateScore,
    collected_provider_refusal,
    finalize_candidate_result,
    refused_case_result,
)
from url4_cloud.benchmarks.contract import CaseResult
from url4_cloud.benchmarks.ifeval.case_evaluation import (
    CHECK_SCHEMA,
    decode_case_evaluation,
)
from url4_cloud.benchmarks.ifeval.definition import REVISION as IFEVAL_REVISION

SCHEMA = CHECK_SCHEMA


class AggregateError(ValueError):
    """The reducer's input is unusable — raised before any scoring."""


def aggregate(
    rows_json: str,
    specs: Mapping[int, Mapping[str, Any]],
    benchmark_id: str,
    case_order: Sequence[int],
) -> dict[str, Any]:
    """Reduce the row array into a `CandidateResult` — exactly one entry per row.

    ``case_order`` is the installed selection order (``load_case_order``): case ids
    are official IFEval keys, which are NOT sorted in case order, so the mapping from
    collected row position to case id must come from ``cases.json`` — never from
    ``sorted(specs)`` or ``index + 1``.
    """

    rows = _rows(rows_json)
    case_results: list[CaseResult] = []
    for index, (raw, case_id) in enumerate(
        zip(rows, _selected_case_ids(rows, specs, case_order), strict=True)
    ):
        spec = specs[case_id]
        record = _first_valid_record(raw, case_id, spec)
        if record is None:
            case_results.append(_failed_case_result(raw, index, case_id, spec))
            continue
        case_results.append(_case_result(case_id, spec, record))
    return finalize_candidate_result(
        benchmark_id=benchmark_id,
        benchmark_revision=IFEVAL_REVISION,
        cases=case_results,
        scorer=_ifeval_score,
    ).as_payload()


def _unscored_result(
    benchmark_id: str,
    benchmark_revision: str,
    cases: Sequence[CaseResult],
) -> dict[str, Any]:
    """Return the complete Evaluation record without fabricating an aggregate score."""

    return finalize_candidate_result(
        benchmark_id=benchmark_id,
        benchmark_revision=benchmark_revision,
        cases=cases,
        scorer=_ifeval_score,
    ).as_payload()


def _failed_case_result(
    row: Any,
    row_index: int,
    case_id: int,
    spec: Mapping[str, Any],
) -> CaseResult:
    """Retain one selected Case whose Candidate Invocation or Grading failed."""

    if refusal := collected_provider_refusal(row):
        return refused_case_result(
            case_id=case_id,
            input=spec["prompt"],
            refusal=refusal,
            metadata={"row_index": row_index},
        )

    error = row.get("error") if isinstance(row, Mapping) else None
    error = error if isinstance(error, Mapping) else {}
    kind = _bounded_text(error.get("kind"), 80)
    code = _bounded_text(error.get("code"), 80) or "invalid_case_evaluation"
    message = _bounded_text(error.get("message"), 200) or (
        "the Case produced no valid IFEval evaluation record"
    )
    metadata: dict[str, Any] = {"row_index": row_index}
    if kind is not None:
        metadata["error_kind"] = kind
    return CaseResult.model_validate(
        {
            "status": "failed",
            "case_id": case_id,
            "input": spec["prompt"],
            "output": None,
            "finish_reason": None,
            "refusal": None,
            "grade": None,
            "failures": [
                {
                    "stage": _failure_stage(code),
                    "code": code,
                    "message": message,
                    "retryable": _retryable(error),
                    "case_id": case_id,
                    "metadata": metadata,
                }
            ],
            "metadata": {},
        }
    )


def _failure_stage(code: str) -> str:
    return (
        "candidate" if code.startswith("provider_") or code.startswith("aigateway_") else "grading"
    )


def _retryable(error: Mapping[str, Any]) -> bool | None:
    retryable = error.get("retryable")
    if isinstance(retryable, bool):
        return retryable
    permanent = error.get("permanent")
    return not permanent if isinstance(permanent, bool) else None


def _bounded_text(value: object, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return " ".join(value.split())[:limit]


def aggregate_corrective(
    rows_json: str,
    specs: Mapping[int, Mapping[str, Any]],
    benchmark_id: str,
    benchmark_revision: str,
    case_order: Sequence[int],
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Reduce corrective-chain rows — one scored entry per case, pass@attempt metrics.

    Selection mirrors the LANL protocol for a single candidate: the EARLIEST attempt
    whose strict checks all pass is the case's answer; a case that never passes is
    scored on its last recorded attempt.
    """

    rows = _rows(rows_json)
    case_results: list[CaseResult] = []
    for index, (raw, case_id) in enumerate(
        zip(rows, _selected_case_ids(rows, specs, case_order), strict=True)
    ):
        spec = specs[case_id]
        records = _attempt_records(raw, case_id, spec, max_attempts)
        if not records:
            case_results.append(_failed_case_result(raw, index, case_id, spec))
            continue
        earliest_pass = min(
            (attempt for attempt, record in records.items() if all(record["strict"])),
            default=0,
        )
        selected_attempt = earliest_pass or max(records)
        case_results.append(
            _corrective_case(
                case_id,
                spec,
                records,
                selected_attempt,
                earliest_pass,
            )
        )
    return finalize_candidate_result(
        benchmark_id=benchmark_id,
        benchmark_revision=benchmark_revision,
        cases=case_results,
        scorer=lambda cases: _ifeval_score(cases, max_attempts=max_attempts),
    ).as_payload()


def _attempt_records(
    row: Any,
    case_id: int,
    spec: Mapping[str, Any],
    max_attempts: int,
) -> dict[int, dict[str, Any]]:
    """Every valid declared attempt in this exact Case Evaluation, keyed by number.

    INVARIANT: a Candidate that echoes a forged record into its answer text cannot
    self-grade. Aggregation never searches nested values: the root envelope and every
    attempt must bind to THIS Case and its private instruction id list.
    """

    expected_ids = list(_instruction_ids(spec))
    records: dict[int, dict[str, Any]] = {}
    attempts = decode_case_evaluation(row, case_id)
    if attempts is None:
        return records
    for record in attempts:
        attempt = _as_int(record.get("attempt"))
        strict = record.get("strict")
        loose = record.get("loose")
        if (
            record.get("valid") is True
            and _as_int(record.get("case_id")) == case_id
            and record.get("instruction_id_list") == expected_ids
            and attempt is not None
            and 1 <= attempt <= max_attempts
            and attempt not in records
            and _is_bool_vector(strict, len(expected_ids))
            and _is_bool_vector(loose, len(expected_ids))
            and _record_content(record, len(expected_ids))
        ):
            records[attempt] = record
    return records


def _corrective_case(
    case_id: int,
    spec: Mapping[str, Any],
    records: Mapping[int, Mapping[str, Any]],
    selected_attempt: int,
    pass_attempt: int,
) -> CaseResult:
    selected = records[selected_attempt]
    result = _case_result(case_id, spec, selected)
    return result.model_copy(
        update={
            "metadata": {
                "selected_attempt": selected_attempt,
                # 0 means no attempt passed every strict Check.
                "pass_attempt": pass_attempt,
                "attempts": [
                    {
                        "attempt": attempt,
                        "output": record["answer"],
                        "finish_reason": record["finish_reason"],
                        "feedback": list(record["violations"]),
                        # The judge's actual coaching for THIS attempt (authored after the
                        # previous round failed); None for attempt 1 and judge-free flows.
                        "judge_feedback": record.get("judge_feedback"),
                    }
                    for attempt, record in sorted(records.items())
                ],
            }
        }
    )


def load_specs(directory: Path) -> dict[int, dict[str, Any]]:
    """Load ``<directory>/<case_id>.json`` for every private instruction spec on disk.

    INVARIANT: an absent or empty directory RAISES — draco's load_rubrics lesson. A
    misconfigured assets path must fail loudly, never reach a client as a terminated
    run carrying a plausible zero.
    """

    specs: dict[int, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        case_id = _as_int(path.stem)
        if case_id is not None:
            specs[case_id] = json.loads(path.read_text(encoding="utf-8"))
    if not specs:
        raise AggregateError(
            f"no instruction specs under {str(directory)!r}; "
            "the installed IFEval assets are incomplete"
        )
    return specs


def load_case_order(root: Path) -> list[int]:
    """The installed selection order — ``cases.json``'s ids, in file order.

    Case ids are official IFEval keys, which are NOT sorted in case order, so this
    file is the only source of "which case is collected row N". Same fail-loud rule
    as ``load_specs``: a missing or malformed ``cases.json`` raises before any
    scoring.
    """

    path = root / "cases.json"
    if not path.is_file():
        raise AggregateError(
            f"no cases.json under {str(root)!r}; the installed IFEval assets are incomplete"
        )
    try:
        cases = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AggregateError(f"cases.json is not JSON: {exc}") from None
    if not isinstance(cases, list) or not cases:
        raise AggregateError("cases.json must be a non-empty JSON array")
    order: list[int] = []
    for entry in cases:
        case_id = _as_int(entry.get("id")) if isinstance(entry, Mapping) else None
        if case_id is None:
            raise AggregateError(f"cases.json entry without an int id: {entry!r}")
        order.append(case_id)
    if len(set(order)) != len(order):
        raise AggregateError("cases.json carries duplicate case ids")
    return order


def _rows(rows_json: str) -> list[Any]:
    try:
        rows = json.loads(rows_json)
    except (TypeError, ValueError) as exc:
        raise AggregateError(f"reducer payload is not JSON: {exc}") from None
    if not isinstance(rows, list):
        raise AggregateError(f"reducer payload must be a JSON array, got {type(rows).__name__}")
    if not rows:
        raise AggregateError("no IFEval rows were produced; the Candidate cannot be scored")
    return rows


def _selected_case_ids(
    rows: Sequence[Any],
    specs: Mapping[int, Mapping[str, Any]],
    case_order: Sequence[int],
) -> list[int]:
    """The prefix of installed Cases selected by the Benchmark's `limit` slice.

    The slice walks ``cases.json`` in file order, so the id for collected row N is
    ``case_order[N]``. Ids are official keys — sorting them would grade rows against
    the wrong specs.
    """

    if len(rows) > len(case_order):
        raise AggregateError(
            f"reducer carried {len(rows)} rows but only {len(case_order)} IFEval cases "
            "are installed"
        )
    selected = list(case_order[: len(rows)])
    missing = [case_id for case_id in selected if case_id not in specs]
    if missing:
        raise AggregateError(
            f"cases.json selects case ids {missing} that have no installed instruction "
            "spec; the installed IFEval assets are incomplete"
        )
    return selected


def _first_valid_record(
    row: Any,
    expected_case_id: int,
    spec: Mapping[str, Any],
) -> dict[str, Any] | None:
    expected_ids = list(_instruction_ids(spec))
    records = decode_case_evaluation(row, expected_case_id)
    if records is None or len(records) != 1:
        return None
    record = records[0]
    strict = record.get("strict")
    loose = record.get("loose")
    if (
        record.get("schema") == SCHEMA
        and record.get("valid") is True
        # INVARIANT: an authentic record for ANOTHER known Case is still not this row's
        # grade. The private instruction vector binds the record to the same Case too.
        and _as_int(record.get("case_id")) == expected_case_id
        and record.get("instruction_id_list") == expected_ids
        and _is_bool_vector(strict, len(expected_ids))
        and _is_bool_vector(loose, len(expected_ids))
        and _record_content(record, len(expected_ids))
    ):
        return record
    return None


def _is_bool_vector(value: object, expected_length: int) -> bool:
    """True only for the exact vector type emitted by deterministic verification."""

    return (
        isinstance(value, list)
        and len(value) == expected_length
        and all(type(item) is bool for item in value)
    )


def _record_content(record: Mapping[str, Any], instruction_count: int) -> bool:
    return (
        isinstance(record.get("answer"), str)
        and "finish_reason" in record
        and (
            record["finish_reason"] is None
            or isinstance(record["finish_reason"], str)
            and bool(record["finish_reason"].strip())
        )
        and isinstance(record.get("descriptions"), list)
        and len(record["descriptions"]) == instruction_count
        and all(isinstance(value, str) and value for value in record["descriptions"])
        and isinstance(record.get("violations"), list)
        and all(isinstance(value, str) for value in record["violations"])
    )


def _case_result(case_id: int, spec: Mapping[str, Any], record: Mapping[str, Any]) -> CaseResult:
    strict = [bool(value) for value in record["strict"]]
    loose = [bool(value) for value in record["loose"]]
    descriptions = record["descriptions"]
    assert isinstance(descriptions, list)
    return CaseResult.model_validate(
        {
            "status": "scored",
            "case_id": case_id,
            "input": spec["prompt"],
            "output": record["answer"],
            "finish_reason": record["finish_reason"],
            "refusal": None,
            "grade": {
                "method": "deterministic",
                "score": float(all(strict)),
                "metrics": {
                    "follow_all_strict": all(strict),
                    "follow_all_loose": all(loose),
                    "strict_checks_passed": sum(strict),
                    "loose_checks_passed": sum(loose),
                },
                "checks": [
                    {
                        "type": "instruction",
                        "id": f"instruction-{index}",
                        "label": descriptions[index - 1],
                        # Check-level verdict in the report schema's vocabulary; the strict
                        # verifier decides it, matching the headline score. Without it a
                        # reader must dig into evidence, and the SDK renders the check as
                        # unjudged.
                        "outcome": "MET" if strict[index - 1] else "UNMET",
                        "evidence": [
                            _verification_evidence(1, "strict", strict[index - 1]),
                            _verification_evidence(2, "loose", loose[index - 1]),
                        ],
                        "metadata": {"instruction_index": index},
                    }
                    for index in range(1, len(strict) + 1)
                ],
            },
            "failures": [],
            "metadata": {},
        }
    )


def _ifeval_score(
    cases: Sequence[CaseResult], *, max_attempts: int | None = None
) -> CandidateScore:
    """Apply IFEval's published accuracy formulas to complete typed Cases."""

    grades = [case.grade for case in cases]
    if any(grade is None or grade.score is None for grade in grades):  # pragma: no cover
        raise AssertionError("IFEval scorer requires complete graded Cases")
    typed_grades = [grade for grade in grades if grade is not None]
    strict_all = [grade.score == 1.0 for grade in typed_grades]
    loose_all = [grade.metrics.get("follow_all_loose") is True for grade in typed_grades]
    strict_flat = [check.outcome == "MET" for grade in typed_grades for check in grade.checks]
    loose_flat = [
        evidence.outcome == "PASS"
        for grade in typed_grades
        for check in grade.checks
        for evidence in check.evidence
        if evidence.metadata.get("mode") == "loose"
    ]
    inst_level_strict = _accuracy(strict_flat)
    metrics: dict[str, Any] = {
        "inst_level_strict_accuracy": inst_level_strict,
        "prompt_level_loose_accuracy": _accuracy(loose_all),
        "inst_level_loose_accuracy": _accuracy(loose_flat),
        "pass_rate": inst_level_strict,
        "coverage": 1.0,
    }
    if max_attempts is not None:
        metrics.update(
            {
                f"pass_at_{attempt}": round(
                    sum(
                        1
                        for case in cases
                        if case.metadata.get("pass_attempt")
                        and case.metadata["pass_attempt"] <= attempt
                    )
                    / len(cases),
                    4,
                )
                for attempt in range(1, max_attempts + 1)
            }
        )
        metrics["corrected_cases"] = sum(
            1 for case in cases if (case.metadata.get("pass_attempt") or 0) > 1
        )
    return CandidateScore(score=_accuracy(strict_all), metrics=metrics)


def _verification_evidence(sequence: int, mode: str, passed: bool) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "producer": {"type": "deterministic", "id": "ifeval/official-verifier"},
        "valid": True,
        "outcome": "PASS" if passed else "FAIL",
        "raw_output": passed,
        "metadata": {"mode": mode},
    }


def _instruction_ids(spec: Mapping[str, Any]) -> Sequence[str]:
    ids = spec.get("instruction_id_list")
    if not isinstance(ids, list) or not ids:
        raise AggregateError("an instruction spec is missing its instruction_id_list")
    return ids


def _accuracy(values: Sequence[bool]) -> float:
    return round(sum(1 for value in values if value) / len(values), 4) if values else 0.0


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "SCHEMA",
    "AggregateError",
    "aggregate",
    "aggregate_corrective",
    "load_case_order",
    "load_specs",
]
