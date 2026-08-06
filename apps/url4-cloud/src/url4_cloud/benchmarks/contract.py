"""Stable names and payloads shared by Benchmark builders and the Runner adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping

CANDIDATE_ROUTE = "/candidate"
CANDIDATE_INPUT_SCHEMA = "screamingface.candidate-input.v1"
CANDIDATE_INVOCATION_SCHEMA = "screamingface.candidate-invocation.v1"
CANDIDATE_RESULT_SCHEMA = "screamingface.candidate-result.v1"
CANDIDATE_MESSAGE_ROLES = frozenset({"system", "developer", "user", "assistant"})


def encode_candidate_invocation(output: str, finish_reason: str | None) -> str:
    """Bind one exact Candidate output to the provider-originated reason it ended."""

    if not isinstance(output, str) or not output.strip():
        raise ValueError("Candidate Invocation output must be non-empty text")
    if finish_reason is not None and (
        not isinstance(finish_reason, str) or not finish_reason.strip()
    ):
        raise ValueError("Candidate Invocation finish_reason must be non-empty text or null")
    return json.dumps(
        {
            "schema": CANDIDATE_INVOCATION_SCHEMA,
            "output": output,
            "finish_reason": finish_reason,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def decode_candidate_invocation(value: str) -> tuple[str, str | None]:
    """Decode the complete internal result returned by the Engine's ``/candidate`` route."""

    try:
        decoded = json.loads(value or "")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Candidate Invocation result is not JSON: {exc}") from None
    if not isinstance(decoded, Mapping) or decoded.get("schema") != CANDIDATE_INVOCATION_SCHEMA:
        raise ValueError("Candidate Invocation result has an unsupported schema")
    if set(decoded) != {"schema", "output", "finish_reason"}:
        raise ValueError("Candidate Invocation result has an invalid shape")
    output = decoded.get("output")
    finish_reason = decoded.get("finish_reason")
    if not isinstance(output, str) or not output.strip():
        raise ValueError("Candidate Invocation output must be non-empty text")
    if finish_reason is not None and (
        not isinstance(finish_reason, str) or not finish_reason.strip()
    ):
        raise ValueError("Candidate Invocation finish_reason must be non-empty text or null")
    return output, finish_reason


__all__ = [
    "CANDIDATE_INPUT_SCHEMA",
    "CANDIDATE_INVOCATION_SCHEMA",
    "CANDIDATE_MESSAGE_ROLES",
    "CANDIDATE_RESULT_SCHEMA",
    "CANDIDATE_ROUTE",
    "decode_candidate_invocation",
    "encode_candidate_invocation",
]
