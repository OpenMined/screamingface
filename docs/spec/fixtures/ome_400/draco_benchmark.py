"""Phase 0 contract example: canonical DRACO benchmark definition."""

from __future__ import annotations

import json

import screamingface as sf

DATASET = "perplexity-ai/draco"
REVISION = "ce076749809027649ebd331bcb70f42bf720d387"
SPLIT = "test"
SOURCE_SHA256 = "e35bfe78cd827fa1d541b79fbc7bc7b91966d3227d8742c83e99d26d4ac4679a"
EXPECTED_CASES = 100
EXPECTED_DOMAINS = 10
EXPECTED_SECTIONS_PER_CASE = 4
EXPECTED_CRITERIA = 3_934

# The definition embeds the official 5,196-byte Appendix C.5 prompt. The abbreviated
# marker keeps this syntax fixture readable; the hash is the normative byte identity.
DRACO_JUDGE_PROMPT = "<official DRACO Appendix C.5 per-criterion judge prompt>"
DRACO_JUDGE_PROMPT_SHA256 = "dbc1ae32e32be6fbc47180b4a246b997d299bb0e25373a8cde87c6461cb2397b"


def load_cases():
    """Ordinary Python owns ingestion and yields only stable sf.Case values."""
    from datasets import load_dataset

    records = load_dataset(DATASET, split=SPLIT, revision=REVISION)
    if len(records) != EXPECTED_CASES:
        raise ValueError(f"draco@1 expected {EXPECTED_CASES} rows, got {len(records)}")

    case_ids = tuple(str(record["id"]) for record in records)
    if any(not case_id for case_id in case_ids) or len(set(case_ids)) != len(case_ids):
        raise ValueError("draco@1 requires unique non-blank source UUIDs")

    # Source order is canonical: `first=N` must reproduce the pipeline's prefix.
    for record, case_id in zip(records, case_ids, strict=True):
        raw_reference = record["answer"]
        reference = json.loads(raw_reference) if isinstance(raw_reference, str) else raw_reference
        yield sf.Case(
            id=case_id,
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
        passes=3,
        params={
            "temperature": 0.2,
            "reasoning": "low",
            "max_tokens": 4096,
        },
    ),
    aggregator=sf.aggregators.Mean(),
    tools=("web_search",),
)
