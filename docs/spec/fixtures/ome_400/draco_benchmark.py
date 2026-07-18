"""Phase 0 contract example: canonical DRACO benchmark definition."""

from __future__ import annotations

import json

import screamingface as sf

DATASET = "perplexity-ai/draco"
REVISION = "<immutable-hugging-face-commit>"
SPLIT = "test"

DRACO_JUDGE_PROMPT = "<official DRACO Appendix C.5 judge prompt>"


def load_cases():
    """Ordinary Python owns ingestion and yields only stable sf.Case values."""
    from datasets import load_dataset

    records = load_dataset(DATASET, split=SPLIT, revision=REVISION)
    for record in records:
        raw_reference = record["answer"]
        reference = (
            json.loads(raw_reference)
            if isinstance(raw_reference, str)
            else raw_reference
        )
        yield sf.Case(
            id=str(record["id"]),
            input=str(record["problem"]),
            reference=reference,
            metadata={"domain": str(record["domain"])},
        )


benchmark = sf.Benchmark(
    "draco@1",
    title="DRACO",
    cases=load_cases,
    grader=sf.graders.Rubric(
        model="gemini/3.1-pro-preview",
        prompt=DRACO_JUDGE_PROMPT,
        passes=5,
        params={
            "temperature": 0.2,
            "reasoning": "low",
            "max_tokens": 4096,
        },
    ),
    aggregator=sf.aggregators.Mean(),
    tools=("web_search",),
)
