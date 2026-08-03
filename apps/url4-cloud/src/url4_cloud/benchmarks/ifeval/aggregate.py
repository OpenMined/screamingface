"""The IFEval cross-row reducer — check records in, `CandidateResult` out.

FEATURE: one url4 expression per Candidate ends in a cross-row reduce that turns every
case's deterministic check into one scored result.
STORY: as a researcher, the number I publish is the IFEval paper's prompt-level strict
accuracy (arXiv:2311.07911).

INVARIANT: `case_count` is EXACT (one entry per selected case) and `failures` is ALWAYS
empty — the SDK's result decoder hard-rejects anything else. A row whose check produced no
record scores as fail-all-instructions: a deterministic checker crash is a harness BUG,
not judge flake, so it may never silently shrink the exam (deliberate divergence from
draco's unscored-never-zero rule, decided in OME-719).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from url4_cloud.benchmarks.contract import CANDIDATE_RESULT_SCHEMA

SCHEMA = "screamingface.ifeval-check.v1"

_RECORD_SPAN_RE = re.compile(r"\{[^{}]*screamingface\.ifeval-check\.v1[^{}]*\}")
"""A balanced, non-nested ``{...}`` span carrying the shared check-record schema.

Check records are flat (lists of strings and booleans, no nested objects), so refusing
nested braces keeps the scan from swallowing surrounding URL4 prose scaffolding.
"""


class AggregateError(ValueError):
    """The reducer's input is unusable — raised before any scoring."""


def aggregate(
    rows_json: str,
    specs: Mapping[int, Mapping[str, Any]],
    benchmark_id: str,
) -> dict[str, Any]:
    """Reduce the row array into a `CandidateResult` — exactly one entry per row."""

    rows = _rows(rows_json)
    case_results: list[dict[str, Any]] = []
    fallback_count = 0
    for index, raw in enumerate(rows):
        record = _first_valid_record(raw, specs)
        if record is None:
            # WHY position is the fallback identity: the Benchmark produced the case list
            # and `on_error=collect` preserves row order, so row N is case N even when the
            # row itself is an error object.
            case_id = index + 1
            spec = specs.get(case_id)
            if spec is None:
                raise AggregateError(
                    f"row {index} has no check record and no spec for case {case_id}; "
                    "the installed IFEval assets are incomplete"
                )
            size = len(_instruction_ids(spec))
            case_results.append(_case_result(case_id, [False] * size, [False] * size))
            fallback_count += 1
            continue
        case_results.append(
            _case_result(
                int(record["case_id"]),
                [bool(value) for value in record["strict"]],
                [bool(value) for value in record["loose"]],
            )
        )
    if case_results and fallback_count == len(case_results):
        raise AggregateError(
            "no row carried a valid IFEval check record; "
            "an all-crash run must be loud, never a plausible zero score"
        )

    strict_all = [case["follow_all_strict"] for case in case_results]
    loose_all = [case["follow_all_loose"] for case in case_results]
    strict_flat = [value for case in case_results for value in case["strict"]]
    loose_flat = [value for case in case_results for value in case["loose"]]
    return {
        "schema": CANDIDATE_RESULT_SCHEMA,
        "benchmark_id": benchmark_id,
        "case_count": len(case_results),
        "score": _accuracy(strict_all),
        "metrics": {
            "inst_level_strict_accuracy": _accuracy(strict_flat),
            "prompt_level_loose_accuracy": _accuracy(loose_all),
            "inst_level_loose_accuracy": _accuracy(loose_flat),
            "cases_checked": len(case_results) - fallback_count,
            "cases_fallback": fallback_count,
        },
        "case_results": case_results,
        "failures": [],
    }


def aggregate_corrective(
    rows_json: str,
    specs: Mapping[int, Mapping[str, Any]],
    benchmark_id: str,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Reduce corrective-chain rows — one scored entry per case, pass@attempt metrics.

    Selection mirrors the LANL protocol for a single candidate: the EARLIEST attempt
    whose strict checks all pass is the case's answer; a case that never passes is
    scored on its last recorded attempt.
    """

    rows = _rows(rows_json)
    case_results: list[dict[str, Any]] = []
    fallback_count = 0
    for index, raw in enumerate(rows):
        case_id = index + 1
        spec = specs.get(case_id)
        if spec is None:
            raise AggregateError(
                f"row {index} has no spec for case {case_id}; "
                "the installed IFEval assets are incomplete"
            )
        records = _attempt_records(raw, case_id, spec, max_attempts)
        if not records:
            size = len(_instruction_ids(spec))
            case_results.append(
                _corrective_case(case_id, max_attempts, 0, [False] * size, [False] * size)
            )
            fallback_count += 1
            continue
        earliest_pass = min(
            (attempt for attempt, record in records.items() if all(record["strict"])),
            default=0,
        )
        selected_attempt = earliest_pass or max(records)
        selected = records[selected_attempt]
        case_results.append(
            _corrective_case(
                case_id,
                selected_attempt,
                earliest_pass,
                [bool(value) for value in selected["strict"]],
                [bool(value) for value in selected["loose"]],
            )
        )
    if case_results and fallback_count == len(case_results):
        raise AggregateError(
            "no row carried a valid IFEval check record; "
            "an all-crash run must be loud, never a plausible zero score"
        )

    strict_all = [case["follow_all_strict"] for case in case_results]
    loose_all = [case["follow_all_loose"] for case in case_results]
    strict_flat = [value for case in case_results for value in case["strict"]]
    loose_flat = [value for case in case_results for value in case["loose"]]
    total = len(case_results)
    pass_at = {
        f"pass_at_{attempt}": (
            round(
                sum(
                    1
                    for case in case_results
                    if case["pass_attempt"] and case["pass_attempt"] <= attempt
                )
                / total,
                4,
            )
            if total
            else 0.0
        )
        for attempt in range(1, max_attempts + 1)
    }
    return {
        "schema": "screamingface.candidate-result.v1",
        "benchmark_id": benchmark_id,
        "case_count": total,
        "score": _accuracy(strict_all),
        "metrics": {
            "inst_level_strict_accuracy": _accuracy(strict_flat),
            "prompt_level_loose_accuracy": _accuracy(loose_all),
            "inst_level_loose_accuracy": _accuracy(loose_flat),
            **pass_at,
            "corrected_cases": sum(1 for case in case_results if case["pass_attempt"] > 1),
            "cases_checked": total - fallback_count,
            "cases_fallback": fallback_count,
        },
        "case_results": case_results,
        "failures": [],
    }


def _attempt_records(
    row: Any,
    case_id: int,
    spec: Mapping[str, Any],
    max_attempts: int,
) -> dict[int, dict[str, Any]]:
    """Every valid check record for this row, keyed by attempt (first per attempt wins).

    INVARIANT: a Candidate that echoes a forged record into its answer text cannot
    self-grade — a record must carry THIS row's case id and the private spec's exact
    instruction id list, which the prompt never reveals.
    """

    expected_ids = list(_instruction_ids(spec))
    text = row if isinstance(row, str) else json.dumps(row)
    records: dict[int, dict[str, Any]] = {}
    for span in _RECORD_SPAN_RE.finditer(text):
        record = _decode_escaped(span.group(0))
        if not isinstance(record, dict) or record.get("schema") != SCHEMA:
            continue
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
            and isinstance(strict, list)
            and isinstance(loose, list)
            and len(strict) == len(expected_ids)
            and len(loose) == len(expected_ids)
        ):
            records[attempt] = record
    return records


def _corrective_case(
    case_id: int,
    selected_attempt: int,
    pass_attempt: int,
    strict: list[bool],
    loose: list[bool],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "selected_attempt": selected_attempt,
        # 0 means "never passed" — kept numeric so case_results stays JSON-simple.
        "pass_attempt": pass_attempt,
        "strict": strict,
        "loose": loose,
        "follow_all_strict": all(strict),
        "follow_all_loose": all(loose),
    }


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


def _rows(rows_json: str) -> list[Any]:
    try:
        rows = json.loads(rows_json)
    except (TypeError, ValueError) as exc:
        raise AggregateError(f"reducer payload is not JSON: {exc}") from None
    if not isinstance(rows, list):
        raise AggregateError(f"reducer payload must be a JSON array, got {type(rows).__name__}")
    return rows


def _first_valid_record(row: Any, specs: Mapping[int, Mapping[str, Any]]) -> dict[str, Any] | None:
    text = row if isinstance(row, str) else json.dumps(row)
    for span in _RECORD_SPAN_RE.finditer(text):
        record = _decode_escaped(span.group(0))
        if not isinstance(record, dict) or record.get("schema") != SCHEMA:
            continue
        case_id = _as_int(record.get("case_id"))
        strict = record.get("strict")
        loose = record.get("loose")
        if (
            record.get("valid") is True
            # A record for a case this run does not own cannot smuggle in a score.
            and case_id in specs
            and isinstance(strict, list)
            and isinstance(loose, list)
            and len(strict) == len(loose)
            and strict
        ):
            return {**record, "case_id": case_id}
    return None


def _decode_escaped(span: str, max_depth: int = 4) -> Any:
    """Parse a span that may be escaped several levels deep, one unescape at a time."""

    text = span
    for _ in range(max_depth):
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            unescaped = text.replace("\\\\", "\\").replace('\\"', '"')
            if unescaped == text:
                return None
            text = unescaped
    return None


def _case_result(case_id: int, strict: list[bool], loose: list[bool]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "strict": strict,
        "loose": loose,
        "follow_all_strict": all(strict),
        "follow_all_loose": all(loose),
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


__all__ = ["SCHEMA", "AggregateError", "aggregate", "aggregate_corrective", "load_specs"]
