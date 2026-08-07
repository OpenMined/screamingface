"""Wire names shared by Engine-owned Benchmarks and Candidate Invocation."""

from __future__ import annotations

import json
from collections.abc import Mapping

CANDIDATE_ROUTE = "/benchmarks/candidate"
# The source name a client binds its Candidate expression under, so the protocol's `$candidate`
# resolves. Published in every Benchmark resource: a client cannot be expected to infer it.
CANDIDATE_BINDING = "candidate"
CANDIDATE_INVOCATION_SCHEMA = "screamingface.candidate-invocation.v1"
CANDIDATE_RESULT_SCHEMA = "screamingface.candidate-result.v1"
FINISH_REASONS = frozenset({"stop", "length", "tool_calls", "content_filter"})


def encode_candidate_invocation(
    output: str,
    finish_reason: str | None,
    refusal: str | None,
) -> str:
    """Encode one Candidate answer without discarding its provider-originated outcome."""

    _validate_candidate_invocation(output, finish_reason, refusal)
    return json.dumps(
        {
            "schema": CANDIDATE_INVOCATION_SCHEMA,
            "output": output,
            "finish_reason": finish_reason,
            "refusal": refusal,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def decode_candidate_invocation(value: str) -> tuple[str, str | None, str | None]:
    """Decode and validate the internal value returned by the Candidate adapter."""

    try:
        decoded = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Candidate Invocation result is not JSON: {exc}") from None
    if not isinstance(decoded, Mapping) or decoded.get("schema") != CANDIDATE_INVOCATION_SCHEMA:
        raise ValueError("Candidate Invocation result has an unsupported schema")
    if set(decoded) != {"schema", "output", "finish_reason", "refusal"}:
        raise ValueError("Candidate Invocation result has an invalid shape")
    output = decoded["output"]
    finish_reason = decoded["finish_reason"]
    refusal = decoded["refusal"]
    _validate_candidate_invocation(output, finish_reason, refusal)
    return output, finish_reason, refusal


def _validate_candidate_invocation(
    output: object,
    finish_reason: object,
    refusal: object,
) -> None:
    if not isinstance(output, str):
        raise ValueError("Candidate Invocation output must be text")
    if finish_reason is not None and (
        not isinstance(finish_reason, str) or finish_reason not in FINISH_REASONS
    ):
        raise ValueError(
            "Candidate Invocation finish_reason must be a supported provider value or null"
        )
    if refusal is not None and (not isinstance(refusal, str) or not refusal.strip()):
        raise ValueError("Candidate Invocation refusal must be non-empty text or null")


__all__ = [
    "CANDIDATE_BINDING",
    "CANDIDATE_INVOCATION_SCHEMA",
    "CANDIDATE_RESULT_SCHEMA",
    "CANDIDATE_ROUTE",
    "FINISH_REASONS",
    "decode_candidate_invocation",
    "encode_candidate_invocation",
]
