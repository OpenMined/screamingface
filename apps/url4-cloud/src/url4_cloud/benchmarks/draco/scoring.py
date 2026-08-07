"""Pure DRACO rubric scoring primitives.

These formulas mirror ``screamingface-benchmarks/benchmarking/graders/rubric.py``
(arXiv:2602.11685 §4.2). They are deliberately isolated from execution framing and
aggregation so protocol math can be reviewed and tested without the URL4 payload
machinery.

INVARIANT: changes that make these formulas more intuitive but diverge from the pinned reference
create a different benchmark and must not land as DRACO.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from statistics import stdev
from typing import Any, Literal

CriterionSelection = Literal["all", "prefix", "axis-balanced"]


def flatten_criteria(rubric: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """Walk rubric sections into criteria with their scoring axis attached."""
    for section in rubric.get("sections", []):
        axis = section.get("id") or section.get("title") or "unknown"
        for criterion in section.get("criteria") or []:
            row = dict(criterion)
            row.setdefault("weight", 0)
            row["axis"] = axis
            yield row


def select_criteria(
    rubric: Mapping[str, Any],
    count: int | None,
    selection: CriterionSelection,
) -> list[dict[str, Any]]:
    """Select the exact rubric subset one protocol will send to its Judge."""

    criteria = list(flatten_criteria(rubric))
    selected_count = _selection_count(criteria, count, selection)
    if selection == "all":
        return criteria
    assert selected_count is not None
    if selection == "prefix":
        return criteria[:selected_count]
    return _axis_balanced(criteria, selected_count)


def _selection_count(
    criteria: Sequence[Mapping[str, Any]],
    count: int | None,
    selection: str,
) -> int | None:
    if selection not in {"all", "prefix", "axis-balanced"}:
        raise ValueError(f"unknown DRACO criterion selection {selection!r}")
    if selection == "all":
        if count is not None:
            raise ValueError("all-criteria selection cannot declare a criterion count")
        return None
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError(f"{selection} selection requires a positive criterion count")
    if count > len(criteria):
        raise ValueError(f"criterion count {count} exceeds rubric size {len(criteria)}")
    return count


def _axis_balanced(
    criteria: Sequence[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    by_axis: dict[str, list[dict[str, Any]]] = {}
    for criterion in criteria:
        by_axis.setdefault(str(criterion["axis"]), []).append(criterion)
    ordered = [
        axis_criteria[offset]
        for offset in range(max(map(len, by_axis.values())))
        for axis_criteria in by_axis.values()
        if offset < len(axis_criteria)
    ]
    return ordered[:count]


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


def axis_pass_rates(rubric: Mapping[str, Any], verdicts: Mapping[str, bool]) -> dict[str, float]:
    """Recompute the unweighted :func:`pass_rate` independently for each axis."""

    by_axis: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for criterion in flatten_criteria(rubric):
        weight = float(criterion.get("weight", 0))
        met = bool(verdicts.get(criterion["id"], False))
        correct, total = by_axis[criterion["axis"]]
        if (weight >= 0 and met) or (weight < 0 and not met):
            correct += 1
        by_axis[criterion["axis"]] = [correct, total + 1]
    return {axis: (correct / total) if total else 0.0 for axis, (correct, total) in by_axis.items()}


def _factual_axis_value(axes: Mapping[str, float]) -> float:
    for axis, value in axes.items():
        normalized = str(axis).lower().replace("_", "-").replace(" ", "-")
        if normalized in {"factual-accuracy", "factualaccuracy"}:
            return float(value)
    return 0.0


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
    """Score each judge pass independently, then report its mean and sample spread."""
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
            "pass_rate_sd": 0.0,
            "accuracy": 0.0,
            "accuracy_pass_rate": 0.0,
            "axis_scores": {},
            "axis_pass_rates": {},
            "coverage": 0.0,
            "coverage_sd": 0.0,
            "n_runs": 0,
        }
    axes: dict[str, list[float]] = defaultdict(list)
    axis_passes: dict[str, list[float]] = defaultdict(list)
    for run in scored:
        for axis, value in run["axis_scores"].items():
            axes[axis].append(value)
        for axis, value in run["axis_pass_rates"].items():
            axis_passes[axis].append(value)
    norms = [run["normalized_score"] for run in scored]
    pass_rates = [run["pass_rate"] for run in scored]
    coverages = [run["coverage"] for run in scored]
    axis_means = {axis: round(_avg(values), 4) for axis, values in axes.items()}
    axis_pass_means = {axis: round(_avg(values), 4) for axis, values in axis_passes.items()}
    return {
        "normalized_score": round(_avg(norms), 4),
        "normalized_score_sd": round(_stdev(norms), 4),
        "pass_rate": round(_avg(pass_rates), 4),
        "pass_rate_sd": round(_stdev(pass_rates), 4),
        "accuracy": round(_factual_axis_value(axis_means), 4),
        "accuracy_pass_rate": round(_factual_axis_value(axis_pass_means), 4),
        "axis_scores": axis_means,
        "axis_pass_rates": axis_pass_means,
        "coverage": round(_avg(coverages), 4),
        "coverage_sd": round(_stdev(coverages), 4),
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
        "axis_pass_rates": axis_pass_rates(restricted, verdicts),
        "coverage": (len(verdicts) / total) if total else 0.0,
    }


def _avg(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return stdev(values)
