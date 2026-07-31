"""DRACO dataset preparation — artifacts and the generated `[data]` table.

FEATURE: a benchmark's declared world is generated from its dataset at image build.
STORY: as a benchmark author, `prepare` turns `perplexity-ai/draco` into cases, private rubrics,
and a `[data]` table I can merge into the image's url4.toml.

The HF download itself is not exercised — `build()` takes rows, so every test here runs offline.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from url4_cloud.benchmarks.draco import prepare

_RUBRIC = {
    "sections": [
        {"id": "Factual Accuracy", "criteria": [{"id": "a1", "weight": 2, "requirement": "x"}]}
    ]
}


def _row(question: str = "What is X?", rubric: object | None = None) -> dict:
    return {
        "problem": question,
        "answer": json.dumps(_RUBRIC) if rubric is None else rubric,
        "domain": "finance",
    }


# --- artifacts ------------------------------------------------------------------


def test_cases_json_carries_id_and_input(tmp_path: Path) -> None:
    prepare.build([_row("Q1"), _row("Q2")], tmp_path, "/draco")

    cases = json.loads((tmp_path / "cases.json").read_text())
    assert cases[0]["id"] == 1
    assert cases[0]["input"] == "Q1"
    assert [c["id"] for c in cases] == [1, 2]


def test_cases_json_never_carries_the_rubric(tmp_path: Path) -> None:
    """INVARIANT: the privacy boundary of the whole design.

    The client receives `cases.json`; the rubric stays in the image. Leaking it here would let a
    Candidate be tuned against the answer key while every test still passed.
    """
    prepare.build([_row()], tmp_path, "/draco")

    body = (tmp_path / "cases.json").read_text()
    assert "Factual Accuracy" not in body
    assert "weight" not in body


def test_each_rubric_is_written_to_its_own_file(tmp_path: Path) -> None:
    prepare.build([_row(), _row()], tmp_path, "/draco")

    assert json.loads((tmp_path / "rubrics" / "1.json").read_text()) == _RUBRIC
    assert (tmp_path / "rubrics" / "2.json").exists()


# --- the generated table --------------------------------------------------------


def test_the_generated_table_declares_one_route_per_artifact(tmp_path: Path) -> None:
    # WHY one per artifact: routing is exact-match, so a wildcard would not resolve.
    prepare.build([_row(), _row(), _row()], tmp_path, "/draco")

    table = tomllib.loads((tmp_path / "url4.data.toml").read_text())["data"]

    assert "/draco/cases" in table
    assert {"/draco/criteria/1", "/draco/criteria/2", "/draco/criteria/3"} <= set(table)


def test_the_cases_route_declares_its_media_type(tmp_path: Path) -> None:
    """Without it a one-line JSON array collapses to a single element and the run benchmarks
    once against a blob instead of once per case."""
    prepare.build([_row()], tmp_path, "/draco")

    table = tomllib.loads((tmp_path / "url4.data.toml").read_text())["data"]
    assert table["/draco/cases"]["media_type"] == "application/json"


def test_the_route_prefix_is_configurable(tmp_path: Path) -> None:
    prepare.build([_row()], tmp_path, "/bench/draco-lite")

    table = tomllib.loads((tmp_path / "url4.data.toml").read_text())["data"]
    assert "/bench/draco-lite/cases" in table


def test_the_generated_table_is_valid_toml_for_many_cases(tmp_path: Path) -> None:
    prepare.build([_row(f"Q{i}") for i in range(50)], tmp_path, "/draco")

    table = tomllib.loads((tmp_path / "url4.data.toml").read_text())["data"]
    assert len(table) == 51  # 50 criteria files + cases


def test_the_weighted_rubric_is_NOT_declared_as_a_route(tmp_path: Path) -> None:
    """INVARIANT: weights must be unreachable from an expression.

    A declared `/draco/rubrics/N` could be fetched into a judge prompt, which is exactly the
    leak `grading_mode: official` exists to prevent. Only `aggregate.py` reads them, off disk.
    """
    prepare.build([_row()], tmp_path, "/draco")

    table = tomllib.loads((tmp_path / "url4.data.toml").read_text())["data"]
    assert not any("rubrics" in path for path in table)


def test_the_judge_facing_criteria_carry_no_weights(tmp_path: Path) -> None:
    prepare.build([_row()], tmp_path, "/draco")

    criteria = json.loads((tmp_path / "criteria" / "1.json").read_text())
    assert criteria == [{"id": "a1", "requirement": "x"}]
    assert "weight" not in json.dumps(criteria)


# --- validation -----------------------------------------------------------------


def test_an_empty_question_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(prepare.PrepareError, match="empty"):
        prepare.build([_row("")], tmp_path, "/draco")


def test_a_rubric_with_no_sections_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(prepare.PrepareError, match="sections"):
        prepare.build([_row(rubric=json.dumps([{"id": "a1"}]))], tmp_path, "/draco")


def test_a_rubric_that_flattens_to_zero_criteria_is_rejected(tmp_path: Path) -> None:
    """It would score every answer 0.0 while looking like a successful run."""
    with pytest.raises(prepare.PrepareError, match="0 criteria"):
        prepare.build([_row(rubric=json.dumps({"sections": []}))], tmp_path, "/draco")


# --- the round trip -------------------------------------------------------------


def test_prepared_rubrics_load_back_into_the_aggregator(tmp_path: Path) -> None:
    """The two halves must agree on the on-disk shape — this is the seam between them."""
    from url4_cloud.benchmarks.draco import aggregate

    prepare.build([_row(), _row()], tmp_path, "/draco")

    rubrics = aggregate.load_rubrics(tmp_path / "rubrics")
    assert set(rubrics) == {1, 2}
    assert aggregate.normalized_score(rubrics[1], {"a1": True}) == 1.0
