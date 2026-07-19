"""Canonical, pinned GPQA Diamond definition loaded with the researcher's HF access."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import cast

from screamingface.aggregators import Mean
from screamingface.benchmark import Benchmark, Case
from screamingface.errors import InvalidBenchmarkError
from screamingface.graders import ExactChoice

DATASET = "Idavidrein/gpqa"
SUBSET = "gpqa_diamond"
SPLIT = "train"
REVISION = "633f5ee89ab8ad4522a9f850766b73f62147ffdd"
EXPECTED_CASES = 198

_REQUIRED_FIELDS = (
    "Record ID",
    "Question",
    "Correct Answer",
    "Incorrect Answer 1",
    "Incorrect Answer 2",
    "Incorrect Answer 3",
    "High-level domain",
    "Subdomain",
)


@dataclass(frozen=True, slots=True)
class _SourceRow:
    id: str
    question: str
    correct: str
    incorrect: tuple[str, str, str]
    domain: str
    subdomain: str


def benchmark() -> Benchmark:
    """Build the public GPQA definition around the process-cached local cases."""

    return Benchmark(
        "gpqa@1",
        title="GPQA Diamond",
        cases=gpqa_cases(),
        grader=ExactChoice(),
        aggregator=Mean(),
    )


@cache
def gpqa_cases() -> tuple[Case, ...]:
    """Load and fully validate GPQA through the caller's Hugging Face session."""

    from datasets import load_dataset

    raw_rows = tuple(
        load_dataset(
            DATASET,
            SUBSET,
            split=SPLIT,
            revision=REVISION,
        )
    )
    source_rows = _validate_source(raw_rows)
    return tuple(_case(row) for row in source_rows)


def _validate_source(raw_rows: tuple[object, ...]) -> tuple[_SourceRow, ...]:
    if len(raw_rows) != EXPECTED_CASES:
        raise InvalidBenchmarkError(f"gpqa@1 expected {EXPECTED_CASES} rows, got {len(raw_rows)}")

    rows: list[_SourceRow] = []
    seen_ids: set[str] = set()
    for position, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            raise InvalidBenchmarkError(f"gpqa@1 row {position} must be a mapping")
        row = cast(Mapping[str, object], raw_row)
        missing = set(_REQUIRED_FIELDS) - set(row)
        if missing:
            raise InvalidBenchmarkError(
                f"gpqa@1 row {position} is missing fields: {sorted(missing)}"
            )

        case_id = _text(row, "Record ID", position)
        if case_id != case_id.strip():
            raise InvalidBenchmarkError(
                f"gpqa@1 row {position} Record ID must not have outer whitespace"
            )
        if case_id in seen_ids:
            raise InvalidBenchmarkError(f"gpqa@1 has duplicate Record ID: {case_id}")
        seen_ids.add(case_id)

        correct = _text(row, "Correct Answer", position)
        incorrect = (
            _text(row, "Incorrect Answer 1", position),
            _text(row, "Incorrect Answer 2", position),
            _text(row, "Incorrect Answer 3", position),
        )
        if correct in incorrect:
            raise InvalidBenchmarkError(
                f"gpqa@1 row {position} correct answer duplicates a distractor"
            )

        rows.append(
            _SourceRow(
                id=case_id,
                question=_text(row, "Question", position),
                correct=correct,
                incorrect=incorrect,
                domain=_text(row, "High-level domain", position),
                subdomain=_text(row, "Subdomain", position),
            )
        )
    return tuple(rows)


def _text(row: Mapping[str, object], field: str, position: int) -> str:
    value = row[field]
    if not isinstance(value, str) or not value.strip():
        raise InvalidBenchmarkError(
            f"gpqa@1 row {position} field {field!r} must be a non-blank string"
        )
    return value


def _case(row: _SourceRow) -> Case:
    tagged_options = (
        (row.correct, True),
        *((answer, False) for answer in row.incorrect),
    )
    ordered = tuple(
        tagged
        for _, tagged in sorted(
            enumerate(tagged_options),
            key=lambda item: (_permutation_key(row.id, item[0]), item[0]),
        )
    )
    rendered = "\n".join(
        f"{chr(65 + option_index)}. {answer}" for option_index, (answer, _) in enumerate(ordered)
    )
    correct_index = next(index for index, (_, is_correct) in enumerate(ordered) if is_correct)
    return Case(
        row.id,
        f"{row.question}\n\n{rendered}\n\nReply with only A, B, C, or D.",
        reference=chr(65 + correct_index),
        metadata={"domain": row.domain, "subdomain": row.subdomain},
    )


def _permutation_key(case_id: str, source_position: int) -> bytes:
    material = f"screamingface:gpqa@1:{case_id}:{source_position}".encode()
    return hashlib.sha256(material).digest()
