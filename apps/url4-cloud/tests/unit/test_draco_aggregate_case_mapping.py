"""The case -> rubric mapping must be PROVABLE, never guessed from row position.

FEATURE: a DRACO run scores each case's answer against that case's rubric.
STORY: as a researcher I need a published score to be the score of the cases I ran, not of
whichever rubrics happened to sit at the same offsets.

`aggregate` learns a row's case id one of two ways: the Engine binds it to the verdict, or it
falls back to the row's POSITION. Position is only defensible when the rows ARE the whole
declared case set — `iteration.on_error=collect` preserves row order and substitutes an error
object in place, so index N is case N+1.

`;iteration.slice=10:20` breaks that, and breaks it silently. The rows are cases 11-20 while the
positions say 1-10, so every case is scored against the WRONG rubric, no `failures` entry is
produced, and the run reports `terminated: succeeded` with a plausible number. `iteration.slice`
is the sanctioned way to size a run — `manifests.py` and `Dockerfile.benchmark` both advertise it,
the latter having REMOVED a build-time case cap in its favour — so this is reachable from the
documented path, not from misuse.

INVARIANT: when a legacy row needs the positional fallback and the row count does not match the
declared rubric set, the mapping is unverifiable and `aggregate` RAISES. It never scores against
a mapping it cannot prove. Current Engine-owned benchmark expressions bind `case_id` after each
Judge call; the model is never trusted to repeat orchestration identity.
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


def test_a_short_row_set_without_an_echoed_case_id_raises() -> None:
    """The `;iteration.slice=10:20` shape — two rows against four declared cases."""
    rows = json.dumps([_row("c3"), _row("c4")])

    with pytest.raises(agg.AggregateError):
        agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")


def test_the_error_names_both_ways_out() -> None:
    """A benchmark operator has exactly two escapes; the message must state them, because the
    alternative it replaces produced a plausible number instead of any message at all."""
    rows = json.dumps([_row("c3"), _row("c4")])

    with pytest.raises(agg.AggregateError) as excinfo:
        agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")

    message = str(excinfo.value)
    assert "case_id" in message
    assert "2" in message and "4" in message  # the counts that disagree


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


def test_a_full_row_set_without_echoed_ids_still_falls_back_to_position() -> None:
    """The unchanged path: rows ARE the declared set, so position is the benchmark's own
    knowledge and stays trustworthy."""
    rows = json.dumps([_row(f"c{n}") for n in (1, 2, 3, 4)])

    result = agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")

    assert result["case_count"] == 4
    assert [c["case_id"] for c in result["case_results"]] == [1, 2, 3, 4]


def test_no_rows_at_all_does_not_trip_the_guard() -> None:
    """An empty payload consults no rubric, so there is no mapping to be wrong about."""
    result = agg.aggregate("[]", rubrics=_RUBRICS, benchmark_id="draco")

    assert result["case_count"] == 0
    assert result["failures"] == []


def test_rows_that_produced_no_verdicts_do_not_trip_the_guard() -> None:
    """A verdict-less row becomes a `failures` entry and never reaches a rubric, so it needs no
    mapping — counting it as unverifiable would turn a partial judge failure into a dead run."""
    rows = json.dumps([_row("c1", case=1), "case\n\ngraded: judge refused"])

    result = agg.aggregate(rows, rubrics=_RUBRICS, benchmark_id="draco")

    assert result["case_count"] == 1
    assert len(result["failures"]) == 1
