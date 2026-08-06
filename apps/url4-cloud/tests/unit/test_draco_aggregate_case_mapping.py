"""The case -> rubric mapping must be PROVABLE, never guessed from row position.

FEATURE: a DRACO run scores each case's answer against that case's rubric.
STORY: as a researcher I need a published score to be the score of the cases I ran, not of
whichever rubrics happened to sit at the same offsets.

The Engine binds `case_id` onto every verdict after the Judge call. Aggregation requires that
identity on every scoreable row and never infers it from row position. That remains correct for
full, sliced, reordered, and partially failed iterations, while keeping orchestration identity
out of the Judge's control.

INVARIANT: every scoreable row carries exactly one unique Engine-bound `case_id`. An invalid
or mismatched row is retained as an ungraded Case; the reducer never guesses or publishes a
partial Candidate score.
"""

from __future__ import annotations

import json

import pytest

from url4_cloud.benchmarks.draco import aggregate as agg
from url4_cloud.benchmarks.draco.case_evaluation import (
    bind_case_evaluation,
    bind_criterion_evaluation,
)
from url4_cloud.benchmarks.draco.records import CASE_SCHEMA, CHECK_SCHEMA


def _rubric(criterion: str) -> dict[str, object]:
    return {
        "sections": [
            {"id": "Factual Accuracy", "criteria": [{"id": criterion, "weight": 1}]},
        ]
    }


# Four declared cases, each with its OWN criterion id — so a mis-pairing cannot score by luck.
_RUBRICS: dict[int, dict[str, object]] = {n: _rubric(f"c{n}") for n in (1, 2, 3, 4)}


def _selected(*case_ids: int) -> list[dict[str, object]]:
    return [{"id": case_id, "input": f"Question {case_id}"} for case_id in case_ids]


def _row(criterion: str, *, case: int | None = None, status: str = "MET") -> object:
    raw_output = json.dumps({"explanation": "fixture verdict", "criterion_status": status})
    verdict: dict[str, object] = {
        "schema": agg.VERDICT_SCHEMA,
        "criterion_id": criterion,
        "sequence": 1,
        "producer_type": "model",
        "producer_id": "fixture-judge",
        "criterion_status": status,
        "valid": True,
        "explanation": "fixture verdict",
        "raw_output": raw_output,
    }
    if case is not None:
        verdict["case_id"] = case
        case_record = {
            "schema": CASE_SCHEMA,
            "case_id": case,
            "input": f"Question {case}",
            "output": f"Answer {case}",
            "finish_reason": "stop",
            "metadata": {},
        }
        check_record = {
            "schema": CHECK_SCHEMA,
            "case_id": case,
            "criterion_id": criterion,
            "criterion_type": "positive",
            "requirement": f"Requirement {criterion}",
        }
        return bind_case_evaluation(
            case,
            [bind_criterion_evaluation(case, case_record, check_record, [verdict])],
        )
    return {"not": "a DRACO Case Evaluation", "verdict": verdict}


# --- the guard ------------------------------------------------------------------


def test_a_short_row_set_without_bound_case_evaluations_is_unscored() -> None:
    """The `;iteration.slice=10:20` shape — two rows against four declared cases."""
    rows = json.dumps([_row("c3"), _row("c4")])

    result = agg.aggregate(
        rows,
        rubrics=_RUBRICS,
        benchmark_id="draco",
        selected_cases=_selected(3, 4),
    )

    assert result["score"] is None
    assert [case["grade"] for case in result["cases"]] == [None, None]


def test_the_failure_names_the_invalid_case_evaluation() -> None:
    rows = json.dumps([_row("c3"), _row("c4")])

    result = agg.aggregate(
        rows,
        rubrics=_RUBRICS,
        benchmark_id="draco",
        selected_cases=_selected(3, 4),
    )

    failure = result["cases"][0]["failures"][0]
    assert failure["code"] == "invalid_case_evaluation"
    assert failure["metadata"]["row_index"] == 0


def test_a_mixed_row_set_retains_the_unverifiable_row() -> None:
    """One echoed id does not vouch for a sibling that has none."""
    rows = json.dumps([_row("c1", case=1), _row("c2")])

    result = agg.aggregate(
        rows,
        rubrics=_RUBRICS,
        benchmark_id="draco",
        selected_cases=_selected(1, 2),
    )

    assert result["score"] is None
    assert result["cases"][0]["grade"]["score"] == 1.0
    assert result["cases"][1]["grade"] is None


# --- what the guard must NOT catch ----------------------------------------------


def test_a_short_row_set_with_bound_case_ids_scores_normally() -> None:
    """INVARIANT: the guard targets an unprovable MAPPING, not a small run.

    This is the shape a sliced run should take, and it must keep working — otherwise the fix
    would forbid `;iteration.slice` outright rather than making it honest.
    """
    rows = json.dumps([_row("c3", case=3), _row("c4", case=4)])

    result = agg.aggregate(
        rows,
        rubrics=_RUBRICS,
        benchmark_id="draco",
        selected_cases=_selected(3, 4),
    )

    assert result["case_count"] == 2
    assert [c["case_id"] for c in result["cases"]] == [3, 4]
    assert result["score"] == 1.0  # each row met ITS OWN case's criterion


def test_a_full_row_set_without_case_evaluations_is_still_unscored() -> None:
    """Completeness does not make row position a durable Case identity."""
    rows = json.dumps([_row(f"c{n}") for n in (1, 2, 3, 4)])

    result = agg.aggregate(
        rows,
        rubrics=_RUBRICS,
        benchmark_id="draco",
        selected_cases=_selected(1, 2, 3, 4),
    )

    assert result["score"] is None


def test_no_rows_at_all_fails_after_the_mapping_guard() -> None:
    """An empty payload has no mapping error, but it still cannot produce a valid result."""
    with pytest.raises(agg.AggregateError, match="no DRACO rows"):
        agg.aggregate("[]", rubrics=_RUBRICS, benchmark_id="draco", selected_cases=[])


def test_rows_with_a_bound_case_but_no_verdict_become_failed_cases() -> None:
    failed = _row("c2", case=2)
    assert isinstance(failed, dict)
    failed["evidence"][0]["schema"] = "not-a-verdict"
    rows = json.dumps([_row("c1", case=1), failed])

    result = agg.aggregate(
        rows,
        rubrics=_RUBRICS,
        benchmark_id="draco",
        selected_cases=_selected(1, 2),
    )

    assert result["case_count"] == 2
    assert result["failures"] == []
    assert result["cases"][1]["grade"] is None
    assert len(result["cases"][1]["failures"]) == 1
    assert result["score"] is None
