"""Phase 0 contract example: canonical GPQA Diamond benchmark definition."""

from __future__ import annotations

import random

import screamingface as sf

DATASET = "Idavidrein/gpqa"
REVISION = "<immutable-hugging-face-commit>"
SPLIT = "train"


def load_cases():
    """Ordinary Python owns ingestion and yields only stable sf.Case values."""
    from datasets import load_dataset

    records = load_dataset(
        DATASET,
        "gpqa_diamond",
        split=SPLIT,
        revision=REVISION,
    )
    for index, record in enumerate(records):
        case_id = f"gpqa-diamond-{index}"
        correct = str(record["Correct Answer"])
        options = [
            correct,
            *(str(record[f"Incorrect Answer {number}"]) for number in range(1, 4)),
        ]

        # Case content is stable; first=N only selects from this canonical order.
        random.Random(f"screamingface:gpqa@1:{case_id}").shuffle(options)
        choices = "\n".join(
            f"{chr(65 + option_index)}. {option}"
            for option_index, option in enumerate(options)
        )
        yield sf.Case(
            id=case_id,
            input=(
                f"{record['Question']}\n\n{choices}\n\nReply with only A, B, C, or D."
            ),
            reference=chr(65 + options.index(correct)),
            metadata={"subject": "science"},
        )


benchmark = sf.Benchmark(
    "gpqa@1",
    title="GPQA Diamond",
    cases=load_cases,
    grader=sf.graders.ExactChoice(),
    aggregator=sf.aggregators.Mean(),
)
