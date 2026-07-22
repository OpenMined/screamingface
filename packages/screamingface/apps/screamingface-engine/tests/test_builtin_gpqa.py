from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
import screamingface as sf

from screamingface_engine.benchmark_definitions import gpqa


def _gpqa_rows(count: int = gpqa.EXPECTED_CASES) -> list[dict[str, object]]:
    return [
        {
            "Record ID": f"record-{index}",
            "Question": f"Which is correct? {index}",
            "Correct Answer": "correct",
            "Incorrect Answer 1": "wrong one",
            "Incorrect Answer 2": "wrong two",
            "Incorrect Answer 3": "wrong three",
            "High-level domain": "Physics",
            "Subdomain": "Mechanics",
        }
        for index in range(count)
    ]


@pytest.fixture(autouse=True)
def clear_gpqa_cache():
    gpqa.gpqa_cases.cache_clear()
    yield
    gpqa.gpqa_cases.cache_clear()


def test_engine_gpqa_definition_is_pinned_cached_and_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def load_dataset(*args: object, **kwargs: object):
        calls.append((args, kwargs))
        return _gpqa_rows()

    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(load_dataset=load_dataset))

    first = gpqa.benchmark()
    second = gpqa.benchmark()
    first_cases = first._materialize_cases()
    second_cases = second._materialize_cases()

    assert first.id == "gpqa@1"
    assert first.title == "GPQA Diamond"
    assert isinstance(first.grader, sf.graders.ExactChoice)
    assert first_cases is second_cases
    assert len(first_cases) == gpqa.EXPECTED_CASES
    assert first_cases[0].id == "record-0"
    assert first_cases[0].input == (
        "Which is correct? 0\n\n"
        "A. correct\n"
        "B. wrong one\n"
        "C. wrong two\n"
        "D. wrong three\n\n"
        "Reply with only A, B, C, or D."
    )
    assert first_cases[0].reference == "A"
    assert first_cases[0].metadata == {"domain": "Physics", "subdomain": "Mechanics"}
    assert first_cases[1].id == "record-1"
    assert first_cases[1].input == (
        "Which is correct? 1\n\n"
        "A. wrong two\n"
        "B. wrong one\n"
        "C. correct\n"
        "D. wrong three\n\n"
        "Reply with only A, B, C, or D."
    )
    assert first_cases[1].reference == "C"
    assert calls == [
        (
            (gpqa.DATASET, gpqa.SUBSET),
            {"split": gpqa.SPLIT, "revision": gpqa.REVISION},
        )
    ]


def test_gpqa_source_requires_the_canonical_row_count() -> None:
    with pytest.raises(sf.InvalidBenchmarkError, match="expected 198 rows, got 197"):
        gpqa._validate_source(tuple(_gpqa_rows(gpqa.EXPECTED_CASES - 1)))


def test_gpqa_source_requires_mapping_rows() -> None:
    rows: list[object] = []
    rows.extend(_gpqa_rows())
    rows[-1] = "not a row"

    with pytest.raises(sf.InvalidBenchmarkError, match="row 197 must be a mapping"):
        gpqa._validate_source(tuple(rows))


def test_gpqa_source_requires_every_field() -> None:
    rows = _gpqa_rows()
    del rows[-1]["Subdomain"]

    with pytest.raises(sf.InvalidBenchmarkError, match=r"missing fields: \['Subdomain'\]"):
        gpqa._validate_source(tuple(rows))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("Question", 42, "field 'Question' must be a non-blank string"),
        (
            "High-level domain",
            "  ",
            "field 'High-level domain' must be a non-blank string",
        ),
        ("Record ID", " record-0 ", "Record ID must not have outer whitespace"),
    ],
)
def test_gpqa_source_requires_strict_nonblank_strings(
    field: str,
    value: object,
    message: str,
) -> None:
    rows = _gpqa_rows()
    rows[0][field] = value

    with pytest.raises(sf.InvalidBenchmarkError, match=message):
        gpqa._validate_source(tuple(rows))


def test_gpqa_source_requires_unique_record_ids() -> None:
    rows = _gpqa_rows()
    rows[-1]["Record ID"] = rows[0]["Record ID"]

    with pytest.raises(sf.InvalidBenchmarkError, match="duplicate Record ID: record-0"):
        gpqa._validate_source(tuple(rows))


def test_gpqa_source_preserves_duplicate_distractors_but_not_a_correct_collision() -> None:
    rows = _gpqa_rows()
    rows[-1]["Incorrect Answer 3"] = rows[-1]["Incorrect Answer 1"]

    normalized = gpqa._validate_source(tuple(rows))

    assert normalized[-1].incorrect == ("wrong one", "wrong two", "wrong one")

    rows[-1]["Incorrect Answer 3"] = rows[-1]["Correct Answer"]
    with pytest.raises(sf.InvalidBenchmarkError, match="correct answer duplicates a distractor"):
        gpqa._validate_source(tuple(rows))
