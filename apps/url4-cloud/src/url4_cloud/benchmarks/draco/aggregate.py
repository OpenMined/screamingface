"""The DRACO cross-row reducer — per-criterion verdicts in, `CandidateResult` out.

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
  support it, and the runner-driven Tavily loop on `kimi-k2.6`, `deepseek-v4-pro` and
  `qwen3.6-plus`, which answer `404` to native search. Both honour the same declared blocklist —
  verified live on both paths — but they are not the same search product, so a candidate that
  answered through Tavily and one that answered natively did not read the same web. A comparison
  ACROSS those two groups carries that caveat; the reference chart used neither exactly.

Neither is visible in the numbers this module emits. A score published as "DRACO-reproduced"
has to state both.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from url4_cloud.benchmarks.contract import CANDIDATE_RESULT_SCHEMA
from url4_cloud.benchmarks.draco.definition import JUDGE_PASSES, REVISION
from url4_cloud.benchmarks.draco.scoring import flatten_criteria, score_case
from url4_cloud.benchmarks.draco.verdict import SCHEMA as VERDICT_SCHEMA

_VERDICT_SPAN_RE = re.compile(r"\{[^{}]*screamingface\.criterion-verdict\.v1[^{}]*\}")
"""A balanced, non-nested ``{...}`` span carrying the shared verdict schema.

The Judge's prompt and raw reply cannot contain this Engine-owned schema marker. Deliberately
non-recursive: a bound verdict is flat, so refusing nested braces keeps the scan from swallowing
the surrounding URL4 prose scaffolding when a Judge emits something unexpected.
"""

COVERAGE_TARGET = 0.95


class AggregateError(ValueError):
    """The reducer's input is unusable — raised before any scoring."""


# --- harvesting verdicts out of the nested payload -------------------------------


def harvest_verdicts(row: Any) -> list[dict[str, Any]]:
    """Every Engine-bound verdict record in one Case's output, in order.

    The row is prose-wrapped once per nesting level (case → criteria → runs), and each level
    JSON-escapes the one below it, so the verdicts sit at varying escape depths inside one
    string.

    INVARIANT: the scaffolding is NEVER parsed. Only balanced ``{...}`` spans carrying the shared
    schema are read; everything between them is ignored. Prompt examples and raw Judge JSON lack
    that marker, so they cannot become verdicts even when they mention ``criterion_status``.
    """
    out: list[dict[str, Any]] = []
    for span in _VERDICT_SPAN_RE.finditer(_as_text_row(row)):
        verdict = _decode_escaped(span.group(0))
        if isinstance(verdict, dict) and verdict.get("schema") == VERDICT_SCHEMA:
            out.append(verdict)
    return out


def _as_text_row(row: Any) -> str:
    return row if isinstance(row, str) else json.dumps(row)


def _decode_escaped(span: str, max_depth: int = 4) -> Any:
    """Parse a span that may be escaped several levels deep, unescaping one level at a time."""
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


def group_runs(verdicts: Sequence[Mapping[str, Any]]) -> list[dict[str, bool]]:
    """Split flat verdicts into one dict per judge PASS, by order of appearance per criterion.

    INVARIANT: the paper scores each pass independently and then means the passes (§4.2).
    Majority-voting the verdicts first would collapse judge disagreement before it reaches the
    score and would make the reported spread meaningless — the spread IS the stability signal.

    A criterion with fewer verdicts than the others simply has no entry in the later runs, so
    it drops out of those runs' rubrics rather than becoming an UNMET.
    """
    seen: dict[str, int] = defaultdict(int)
    runs: list[dict[str, bool]] = []
    for verdict in verdicts:
        criterion_id = verdict.get("criterion_id") or verdict.get("id")
        if criterion_id is None:
            continue
        key = str(criterion_id)
        index = seen[key]
        seen[key] += 1
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
        ):
            continue
        accepted.append({**verdict, "criterion_id": str(criterion_id), "criterion_status": status})
    return accepted


def case_id_of(verdicts: Sequence[Mapping[str, Any]]) -> int | None:
    """Return the Case identity bound onto the verdict by the Engine."""
    for verdict in verdicts:
        case_id = _as_int(verdict.get("case_id"))
        if case_id is not None:
            return case_id
    return None


# --- the reduction ---------------------------------------------------------------


def aggregate(
    rows_json: str,
    rubrics: Mapping[int, Mapping[str, Any]],
    benchmark_id: str,
    judge_passes: int = JUDGE_PASSES,
    benchmark_revision: str = REVISION,
) -> dict[str, Any]:
    """Reduce the row array into a `CandidateResult` — one row per case.

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
    # INVARIANT: absence of evaluated Cases is an execution failure, not Candidate score zero.
    if not rows:
        raise AggregateError("no DRACO rows were collected; the Candidate cannot be scored")

    # Harvested ONCE, before scoring: the mapping guard below needs to know which rows carry an
    # echoed id, and re-scanning a multi-hundred-KB payload to find out would double the only
    # expensive step in this module.
    harvested_rows = [harvest_verdicts(raw) for raw in rows]
    _require_verifiable_mapping(harvested_rows)

    case_results, failures = _aggregate_rows(rows, harvested_rows, rubrics, judge_passes)
    if not case_results:
        raise AggregateError(_no_scored_cases_message(rows, failures))

    return {
        "schema": CANDIDATE_RESULT_SCHEMA,
        "benchmark_id": benchmark_id,
        "benchmark_revision": benchmark_revision,
        "case_count": len(case_results),
        "score": _mean(case_results, "normalized_score"),
        "metrics": {
            "normalized_score_sd": _mean(case_results, "normalized_score_sd"),
            "pass_rate": _mean(case_results, "pass_rate"),
            "coverage": _mean(case_results, "coverage"),
            "coverage_target": COVERAGE_TARGET,
            "n_runs": max((int(c["n_runs"]) for c in case_results), default=0),
            "verdicts_expected": _sum(case_results, "verdicts_expected"),
            "verdicts_accepted": _sum(case_results, "verdicts_accepted"),
            "verdicts_rejected": _sum(case_results, "verdicts_rejected"),
            "verdicts_invalid": _sum(case_results, "verdicts_invalid"),
            "verdicts_missing": _sum(case_results, "verdicts_missing"),
        },
        "axis_scores": _mean_axes(case_results),
        "case_results": case_results,
        "failures": failures,
    }


def _aggregate_rows(
    raw_rows: Sequence[Any],
    harvested_rows: Sequence[Sequence[Mapping[str, Any]]],
    rubrics: Mapping[int, Mapping[str, Any]],
    judge_passes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    case_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, records in enumerate(harvested_rows):
        if not records:
            failures.append(_row_failure(raw_rows[index], index, raw_rows, rubrics))
            continue
        case_id = case_id_of(records)
        if case_id is None:  # pragma: no cover - sealed by _require_verifiable_mapping
            raise AssertionError("a scored DRACO row must carry its Engine-bound case_id")
        rubric = rubrics.get(case_id)
        if rubric is None:
            failures.append({"index": index, "case_id": case_id, "reason": "unknown case_id"})
            continue
        verdicts = valid_verdicts(rubric, records, case_id)
        if not verdicts:
            failures.append(
                {
                    "index": index,
                    "case_id": case_id,
                    "reason": "no valid judge verdicts in row",
                }
            )
            continue
        case_results.append(_case_result(case_id, rubric, records, verdicts, judge_passes))
    return case_results, failures


def _row_failure(
    row: Any,
    index: int,
    rows: Sequence[Any],
    rubrics: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    failure: dict[str, Any] = {"index": index, "reason": "no judge verdicts in row"}
    error = row.get("error") if isinstance(row, Mapping) else None
    if not isinstance(error, Mapping):
        return failure
    failure["reason"] = "Candidate Case execution failed"
    selected = _bounded_error(error)
    if selected:
        failure["error"] = selected
    if len(rows) == len(rubrics):
        failure["case_id"] = sorted(rubrics)[index]
    return failure


def _bounded_error(error: Mapping[str, Any]) -> dict[str, str]:
    limits = {"kind": 80, "code": 80, "message": 200}
    return {
        field: " ".join(value.split())[:limit]
        for field, limit in limits.items()
        if isinstance((value := error.get(field)), str) and value.strip()
    }


def _no_scored_cases_message(rows: Sequence[Any], failures: Sequence[Mapping[str, Any]]) -> str:
    """Keep a bounded trace of collected execution errors when every Case failed."""
    base = "no row carried a valid DRACO judge verdict; the Candidate cannot be scored"
    details: list[str] = []
    for index, row in enumerate(rows):
        error = row.get("error") if isinstance(row, Mapping) else None
        if not isinstance(error, Mapping):
            continue
        message = error.get("message")
        if not isinstance(message, str) or not message.strip():
            continue
        clean = " ".join(message.split())[:200]
        kind = error.get("kind")
        clean_kind = " ".join(kind.split())[:80] if isinstance(kind, str) else ""
        detail = f"{clean_kind}: {clean}" if clean_kind else clean
        details.append(f"row {index + 1}: {detail}")
        if len(details) == 3:
            break
    if not details:
        details = [
            f"row {int(failure['index']) + 1}: {failure['reason']}" for failure in failures[:3]
        ]
    return f"{base}; collected row error: {'; '.join(details)}" if details else base


def _case_result(
    case_id: int,
    rubric: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    verdicts: Sequence[Mapping[str, Any]],
    judge_passes: int,
) -> dict[str, Any]:
    expected = sum(1 for _ in flatten_criteria(rubric)) * judge_passes
    accepted = len(verdicts)
    return {
        "case_id": case_id,
        **score_case(rubric, group_runs(verdicts)),
        "verdicts_expected": expected,
        "verdicts_accepted": accepted,
        "verdicts_rejected": max(expected - accepted, 0),
        "verdicts_invalid": max(len(records) - accepted, 0),
        "verdicts_missing": max(expected - len(records), 0),
    }


def _require_verifiable_mapping(
    harvested: Sequence[Sequence[Mapping[str, Any]]],
) -> None:
    """Require one unique Engine-bound Case identity for every scoreable row."""

    claimed: dict[int, int] = {}
    for index, verdicts in enumerate(harvested):
        if not verdicts:
            continue
        ids = [_as_int(verdict.get("case_id")) for verdict in verdicts]
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
        claimed[case_id] = index


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mean(case_results: Sequence[Mapping[str, Any]], key: str) -> float:
    if not case_results:
        return 0.0
    return round(sum(float(c[key]) for c in case_results) / len(case_results), 4)


def _sum(case_results: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(int(case[key]) for case in case_results)


def _mean_axes(case_results: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    totals: dict[str, list[float]] = defaultdict(list)
    for case in case_results:
        for axis, score in case["axis_scores"].items():
            totals[axis].append(float(score))
    return {axis: round(sum(v) / len(v), 4) for axis, v in totals.items()}


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
