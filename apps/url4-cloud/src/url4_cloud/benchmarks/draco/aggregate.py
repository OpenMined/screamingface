"""The DRACO cross-row reducer — per-criterion verdicts in, `CandidateResult` out.

FEATURE: one url4 expression per Candidate ends in a cross-row reduce that turns every case's
judge verdicts into one scored result.
STORY: as a researcher, the number I publish is the DRACO paper's `normalized_score`.

Invoked as a declared `[commands]` route in the reducer position::

    (…iteration…)!/benchmark(aggregate)!'x'

    context ("aggregate")  →  {context}, also stdin
    intent (row array)     →  {intent}, the JSON array of every row's judge output

INVARIANT — the scoring formulas mirror `screamingface-benchmarks/benchmarking/graders/rubric.py`
(arXiv:2602.11685 §4.2) EXACTLY. Do not "improve" them. A different formula is a different
benchmark, and a leaderboard number computed here must mean what the paper says it means.

The Client expression follows the paper's ``official`` protocol: one judge call per criterion,
three independent passes, with weights and sibling criteria hidden from the judge.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_RUBRICS_DIR = "/opt/benchmarks/draco/rubrics"
"""Where a BENCHMARK IMAGE puts them (see Dockerfile.benchmark). Only a fallback.

INVARIANT: the path is OPERATOR-controlled — argv, then `URL4_BENCHMARK_RUBRICS`, then this.
It is never taken from the expression: a caller-supplied path would let any run point the
aggregator at any file on the Job's disk.
"""

RUBRICS_DIR_ENV = "URL4_BENCHMARK_RUBRICS"

_VERDICT_SPAN_RE = re.compile(r"\{[^{}]*criterion_status[^{}]*\}")
"""A balanced, non-nested ``{...}`` span mentioning ``criterion_status``.

Deliberately non-recursive: a verdict is a FLAT object, so refusing nested braces keeps the
scan from swallowing the surrounding scaffolding when the judge emits something unexpected.
"""


class AggregateError(ValueError):
    """The reducer's input is unusable — raised before any scoring."""


# --- rubric walking -------------------------------------------------------------


def flatten_criteria(rubric: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """Walk ``{"sections": [{"criteria": [...]}]}`` into criteria with their axis attached.

    The axis is the section's ``id``, falling back to its ``title`` — it is what
    :func:`axis_scores` groups by, and what the paper calls a rubric section (Factual Accuracy,
    Breadth & Depth, Presentation Quality, Citation Quality).
    """
    for section in rubric.get("sections", []):
        axis = section.get("id") or section.get("title") or "unknown"
        for criterion in section.get("criteria") or []:
            row = dict(criterion)
            row.setdefault("weight", 0)
            row["axis"] = axis
            yield row


# --- the paper's three metrics --------------------------------------------------


def normalized_score(rubric: Mapping[str, Any], verdicts: Mapping[str, bool]) -> float:
    """Weight-aware score in [0, 1] — ``clamp(Σ MET·w / Σ w⁺)``.

    A MET positive criterion rewards; a MET NEGATIVE criterion penalises (its weight is negative,
    so it subtracts). The denominator is the positive weights ALONE — the maximum reachable
    numerator, i.e. every positive MET and every negative UNMET.

    An all-negative rubric is undefined in the paper; 0.0 is returned rather than interpolating a
    harness-specific fallback that would drift from published numbers.
    """
    weighted_sum = 0.0
    denom_pos = 0.0
    for criterion in flatten_criteria(rubric):
        weight = float(criterion.get("weight", 0))
        met = bool(verdicts.get(criterion["id"], False))
        if weight > 0:
            denom_pos += weight
            if met:
                weighted_sum += weight
        elif weight < 0 and met:
            weighted_sum += weight  # negative: subtracts
    if denom_pos <= 0:
        return 0.0
    return max(0.0, min(1.0, weighted_sum / denom_pos))


def pass_rate(rubric: Mapping[str, Any], verdicts: Mapping[str, bool]) -> float:
    """Unweighted fraction of criteria handled correctly.

    Correct means MET for a positive criterion and UNMET for a negative one — an anti-pattern
    successfully avoided counts exactly as much as a requirement met.
    """
    n_correct = 0
    n_total = 0
    for criterion in flatten_criteria(rubric):
        weight = float(criterion.get("weight", 0))
        met = bool(verdicts.get(criterion["id"], False))
        if (weight >= 0 and met) or (weight < 0 and not met):
            n_correct += 1
        n_total += 1
    return (n_correct / n_total) if n_total else 0.0


def axis_scores(rubric: Mapping[str, Any], verdicts: Mapping[str, bool]) -> dict[str, float]:
    """:func:`normalized_score` recomputed per rubric section."""
    by_axis: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])  # [achieved, achievable]
    for criterion in flatten_criteria(rubric):
        weight = float(criterion.get("weight", 0))
        met = bool(verdicts.get(criterion["id"], False))
        achieved, achievable = by_axis[criterion["axis"]]
        if weight >= 0:
            achievable += weight
            if met:
                achieved += weight
        elif met:
            achieved += weight
        by_axis[criterion["axis"]] = [achieved, achievable]
    return {
        axis: (max(0.0, min(1.0, achieved / achievable)) if achievable > 0 else 0.0)
        for axis, (achieved, achievable) in by_axis.items()
    }


def _restrict(rubric: Mapping[str, Any], judged_ids: Sequence[str]) -> dict[str, Any]:
    """The rubric minus criteria that produced no verdict.

    INVARIANT: an unjudged criterion drops out of BOTH numerator and denominator. Scoring it as
    UNMET instead would keep its weight in the denominator, so a judge parse or transport failure
    would deflate the score in proportion to the failure rate — a benchmark that reports lower
    numbers when the harness is flaky, which is worse than reporting fewer cases.
    """
    keep = set(judged_ids)
    return {
        "sections": [
            {
                **section,
                "criteria": [c for c in (section.get("criteria") or []) if c.get("id") in keep],
            }
            for section in rubric.get("sections", [])
        ]
    }


def score_case(rubric: Mapping[str, Any], runs: Sequence[Mapping[str, bool]]) -> dict[str, Any]:
    """Score every judge PASS independently, then report the mean and the spread.

    INVARIANT: the paper scores each pass and then means the passes (§4.2). Majority-voting the
    verdicts first would collapse judge disagreement before it reaches the score, and the spread
    is the judge-stability signal — a high sd means the passes disagreed, which a single averaged
    number destroys.

    The spread is the POPULATION standard deviation, matching the harness's ``np.std`` default.
    """
    total = sum(1 for _ in flatten_criteria(rubric))
    scored = [_score_one_run(rubric, verdicts, total) for verdicts in runs]
    if not scored:
        return {
            "normalized_score": 0.0,
            "normalized_score_sd": 0.0,
            "pass_rate": 0.0,
            "axis_scores": {},
            "coverage": 0.0,
            "n_runs": 0,
        }
    axes: dict[str, list[float]] = defaultdict(list)
    for run in scored:
        for axis, value in run["axis_scores"].items():
            axes[axis].append(value)
    norms = [run["normalized_score"] for run in scored]
    return {
        "normalized_score": round(_avg(norms), 4),
        "normalized_score_sd": round(_stdev(norms), 4),
        "pass_rate": round(_avg([run["pass_rate"] for run in scored]), 4),
        "axis_scores": {axis: round(_avg(v), 4) for axis, v in axes.items()},
        "coverage": round(_avg([run["coverage"] for run in scored]), 4),
        "n_runs": len(scored),
    }


def _score_one_run(
    rubric: Mapping[str, Any], verdicts: Mapping[str, bool], total: int
) -> dict[str, Any]:
    restricted = _restrict(rubric, list(verdicts))
    return {
        "normalized_score": normalized_score(restricted, verdicts),
        "pass_rate": pass_rate(restricted, verdicts),
        "axis_scores": axis_scores(restricted, verdicts),
        "coverage": (len(verdicts) / total) if total else 0.0,
    }


def _avg(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _avg(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


# --- harvesting verdicts out of the nested payload -------------------------------


def harvest_verdicts(row: Any) -> list[dict[str, Any]]:
    """Every judge verdict in one case's row, in order.

    The row is prose-wrapped once per nesting level (case → criteria → runs), and each level
    JSON-escapes the one below it, so the verdicts sit at varying escape depths inside one
    string.

    INVARIANT: the scaffolding is NEVER parsed. Only balanced ``{...}`` spans carrying
    ``criterion_status`` are read; everything between them is ignored. The prose framing is an
    engine formatting detail that has already changed once during this design — a regex over it
    would be a contract that breaks silently, whereas an absent verdict is loudly absent.
    """
    out: list[dict[str, Any]] = []
    for span in _VERDICT_SPAN_RE.finditer(_as_text_row(row)):
        verdict = _decode_escaped(span.group(0))
        if isinstance(verdict, dict) and "criterion_status" in verdict:
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


def case_id_of(verdicts: Sequence[Mapping[str, Any]]) -> int | None:
    """The case id the judge echoed, if any — ``None`` falls back to row position."""
    for verdict in verdicts:
        case_id = _as_int(verdict.get("case_id"))
        if case_id is not None:
            return case_id
    return None


# --- the reduction ---------------------------------------------------------------


def aggregate(
    rows_json: str, rubrics: Mapping[int, Mapping[str, Any]], benchmark_id: str
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

    case_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        verdicts = harvest_verdicts(raw)
        if not verdicts:
            failures.append({"index": index, "reason": "no judge verdicts in row"})
            continue
        # WHY position is a legitimate fallback: the BENCHMARK produced the case list, and row
        # order is preserved — `iteration.on_error=collect` substitutes an error object in place
        # rather than dropping a row. The echoed id still wins when present, because it survives
        # a future change to row ordering that position would not.
        case_id = case_id_of(verdicts)
        if case_id is None:
            case_id = index + 1
        rubric = rubrics.get(case_id)
        if rubric is None:
            failures.append({"index": index, "case_id": case_id, "reason": "unknown case_id"})
            continue
        case_results.append({"case_id": case_id, **score_case(rubric, group_runs(verdicts))})

    return {
        "schema": "screamingface.candidate-result.v1",
        "benchmark_id": benchmark_id,
        "case_count": len(case_results),
        "score": _mean(case_results, "normalized_score"),
        "metrics": {
            "normalized_score": _mean(case_results, "normalized_score"),
            "normalized_score_sd": _mean(case_results, "normalized_score_sd"),
            "pass_rate": _mean(case_results, "pass_rate"),
            "coverage": _mean(case_results, "coverage"),
            "n_runs": max((int(c["n_runs"]) for c in case_results), default=0),
        },
        "axis_scores": _mean_axes(case_results),
        "case_results": case_results,
        "failures": failures,
    }


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mean(case_results: Sequence[Mapping[str, Any]], key: str) -> float:
    if not case_results:
        return 0.0
    return round(sum(float(c[key]) for c in case_results) / len(case_results), 4)


def _mean_axes(case_results: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    totals: dict[str, list[float]] = defaultdict(list)
    for case in case_results:
        for axis, score in case["axis_scores"].items():
            totals[axis].append(float(score))
    return {axis: round(sum(v) / len(v), 4) for axis, v in totals.items()}


# --- CLI --------------------------------------------------------------------------


def rubrics_dir(explicit: Path | None) -> Path:
    """Resolve where the rubrics live: argv, then the environment, then the image default.

    The `[data]` routes get their absolute paths from `prepare --out`, so the rubrics path has to
    come from the same deployment. Baking it into `url4.toml` made the two disagree the moment
    the runner ran anywhere but the image.
    """
    if explicit is not None:
        return explicit
    return Path(os.environ.get(RUBRICS_DIR_ENV) or DEFAULT_RUBRICS_DIR)


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
            f"no rubrics under {str(directory)!r} — set {RUBRICS_DIR_ENV} (or pass --rubrics) to "
            "the directory this benchmark's `prepare` wrote"
        )
    return rubrics


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="draco-aggregate", description=__doc__)
    parser.add_argument("--operation", default="aggregate", help="the {context} token")
    parser.add_argument("--args", default="[]", help="the {intent} payload — the JSON row array")
    parser.add_argument("--rubrics", type=Path, default=None)
    parser.add_argument("--benchmark-id", default="draco-lite")
    args = parser.parse_args(argv)

    if args.operation.strip() != "aggregate":
        print(f"unsupported operation {args.operation!r}", file=sys.stderr)
        return 2
    try:
        result = aggregate(args.args, load_rubrics(rubrics_dir(args.rubrics)), args.benchmark_id)
    except AggregateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    # stdout IS the route's result — nothing else may be printed here.
    print(json.dumps(result))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
