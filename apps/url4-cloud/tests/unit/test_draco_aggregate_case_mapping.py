"""The case -> rubric mapping must be PROVABLE, never guessed from row position.

FEATURE: a DRACO run scores each case's answer against that case's rubric.
STORY: as a researcher I need a published score to be the score of the cases I ran, not of
whichever rubrics happened to sit at the same offsets.

The Engine binds `case_id` onto every verdict after the Judge call. Aggregation requires that
identity on every scoreable row and never infers it from row position. That remains correct for
full, sliced, reordered, and partially failed iterations, while keeping orchestration identity
out of the Judge's control.

INVARIANT: every scoreable row carries exactly one unique Engine-bound `case_id`. Missing,
mixed, or duplicate identities raise before scoring; the reducer never guesses.
"""

from __future__ import annotations

import json

import pytest

from url4_cloud.benchmarks.draco import aggregate as agg


def _rubric(criterion: str) -> dict[str, object]:
    return {
        "sections": [
            {"id": "Factual Accuracy", "criteria": [{"id": criterion, "weight": 1}]},
        ]
    }


# Four declared cases, each with its OWN criterion id — so a mis-pairing cannot score by luck.
_RUBRICS: dict[int, dict[str, object]] = {n: _rubric(f"c{n}") for n in (1, 2, 3, 4)}


def _row(criterion: str, *, case: int | None = None, status: str = "MET") -> str:
    verdict: dict[str, object] = {
        "schema": agg.VERDICT_SCHEMA,
        "criterion_id": criterion,
        "criterion_status": status,
        "valid": True,
        "explanation": "fixture verdict",
    }
    if case is not None:
        verdict["case_id"] = case
    return f"case\n\ngraded: [{json.dumps(json.dumps(verdict))}]"


# --- the guard ------------------------------------------------------------------


def test_a_short_row_set_without_a_bound_case_id_raises() -> None:
    """The `;iteration.slice=10:20` shape — two rows against four declared cases."""
    rows = json.dumps([_row("c3"), _row("c4")])

    with pytest.raises(agg.AggregateError):
        agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")


def test_the_error_names_the_missing_engine_binding() -> None:
    rows = json.dumps([_row("c3"), _row("c4")])

    with pytest.raises(agg.AggregateError) as excinfo:
        agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")

    message = str(excinfo.value)
    assert "Engine-bound case_id" in message
    assert "row 0" in message


def test_a_mixed_row_set_raises_on_the_unverifiable_row() -> None:
    """One echoed id does not vouch for a sibling that has none."""
    rows = json.dumps([_row("c1", case=1), _row("c2")])

    with pytest.raises(agg.AggregateError):
        agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")


# --- what the guard must NOT catch ----------------------------------------------


def test_a_short_row_set_with_bound_case_ids_scores_normally() -> None:
    """INVARIANT: the guard targets an unprovable MAPPING, not a small run.

    This is the shape a sliced run should take, and it must keep working — otherwise the fix
    would forbid `;iteration.slice` outright rather than making it honest.
    """
    rows = json.dumps([_row("c3", case=3), _row("c4", case=4)])

    result = agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")

    assert result["case_count"] == 2
    assert [c["case_id"] for c in result["case_results"]] == [3, 4]
    assert result["score"] == 1.0  # each row met ITS OWN case's criterion


def test_a_full_row_set_without_bound_ids_is_still_rejected() -> None:
    """Completeness does not make row position a durable Case identity."""
    rows = json.dumps([_row(f"c{n}") for n in (1, 2, 3, 4)])

    with pytest.raises(agg.AggregateError, match="Engine-bound case_id"):
        agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")


def test_no_rows_at_all_fails_after_the_mapping_guard() -> None:
    """An empty payload has no mapping error, but it still cannot produce a valid result."""
    with pytest.raises(agg.AggregateError, match="no DRACO rows"):
        agg.aggregate("[]", rubrics=_RUBRICS, benchmark_id="draco")


def test_rows_that_produced_no_verdicts_do_not_trip_the_guard() -> None:
    """A verdict-less row becomes a `failures` entry and never reaches a rubric, so it needs no
    mapping — counting it as unverifiable would turn a partial judge failure into a dead run."""
    rows = json.dumps([_row("c1", case=1), "case\n\ngraded: judge refused"])

    result = agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")

    assert result["case_count"] == 1
    assert len(result["failures"]) == 1
