"""Phase 0 contract example: canonical GPQA Diamond benchmark definition."""

from __future__ import annotations

import hashlib

import screamingface as sf

DATASET = "Idavidrein/gpqa"
REVISION = "633f5ee89ab8ad4522a9f850766b73f62147ffdd"
SPLIT = "train"
EXPECTED_CASES = 198


def _permutation_key(case_id: str, source_position: int) -> bytes:
    material = f"screamingface:gpqa@1:{case_id}:{source_position}".encode()
    return hashlib.sha256(material).digest()


def load_cases():
    """Ordinary Python owns ingestion and yields only stable sf.Case values."""
    from datasets import load_dataset

    records = load_dataset(
        DATASET,
        "gpqa_diamond",
        split=SPLIT,
        revision=REVISION,
    )
    if len(records) != EXPECTED_CASES:
        raise ValueError(f"gpqa@1 expected {EXPECTED_CASES} rows, got {len(records)}")

    case_ids = tuple(str(record["Record ID"]) for record in records)
    if any(not case_id for case_id in case_ids) or len(set(case_ids)) != len(case_ids):
        raise ValueError("gpqa@1 requires unique non-blank source Record ID values")

    for record, case_id in zip(records, case_ids, strict=True):
        correct = str(record["Correct Answer"])
        tagged_options = [
            (correct, True),
            *((str(record[f"Incorrect Answer {number}"]), False) for number in range(1, 4)),
        ]

        # This is stable across Python versions and processes. `first=N` selects
        # from source order; it never changes this per-record permutation.
        options = [
            tagged
            for _, tagged in sorted(
                enumerate(tagged_options),
                key=lambda item: _permutation_key(case_id, item[0]),
            )
        ]
        choices = "\n".join(
            f"{chr(65 + option_index)}. {option_text}"
            for option_index, (option_text, _) in enumerate(options)
        )
        yield sf.Case(
            id=case_id,
            input=(f"{record['Question']}\n\n{choices}\n\nReply with only A, B, C, or D."),
            reference=chr(65 + next(i for i, (_, is_correct) in enumerate(options) if is_correct)),
            metadata={
                "domain": str(record["High-level domain"]),
                "subdomain": str(record["Subdomain"]),
            },
        )


benchmark = sf.Benchmark(
    "gpqa@1",
    title="GPQA Diamond",
    cases=load_cases,
    grader=sf.graders.ExactChoice(),
    aggregator=sf.aggregators.Mean(),
)
