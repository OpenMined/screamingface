"""Pure DRACO rubric scoring primitives.

These formulas mirror ``screamingface-benchmarks/benchmarking/graders/rubric.py``
(arXiv:2602.11685 §4.2). They are deliberately isolated from execution framing and
aggregation so protocol math can be reviewed and tested without the URL4 payload
machinery.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from typing import Any


def flatten_criteria(rubric: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """Walk rubric sections into criteria with their scoring axis attached."""
    for section in rubric.get("sections", []):
        axis = section.get("id") or section.get("title") or "unknown"
        for criterion in section.get("criteria") or []:
            row = dict(criterion)
            row.setdefault("weight", 0)
            row["axis"] = axis
            yield row


def normalized_score(rubric: Mapping[str, Any], verdicts: Mapping[str, bool]) -> float:
    """Weight-aware score in [0, 1] — ``clamp(Σ MET·w / Σ w⁺)``."""
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
            weighted_sum += weight
    if denom_pos <= 0:
        return 0.0
    return max(0.0, min(1.0, weighted_sum / denom_pos))


def pass_rate(rubric: Mapping[str, Any], verdicts: Mapping[str, bool]) -> float:
    """Unweighted fraction of positive criteria met and negative criteria avoided."""
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
    """Recompute :func:`normalized_score` independently for each rubric section."""
    by_axis: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
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
    """Remove unjudged criteria from both the scoring numerator and denominator."""
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


def score_case(
    rubric: Mapping[str, Any],
    runs: Sequence[Mapping[str, bool]],
    *,
    criteria_expected: int | None = None,
) -> dict[str, Any]:
    """Score each judge pass independently, then report its mean and population spread."""
    total = (
        criteria_expected
        if criteria_expected is not None
        else sum(1 for _ in flatten_criteria(rubric))
    )
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
        "axis_scores": {axis: round(_avg(values), 4) for axis, values in axes.items()},
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
    return (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5
