"""Wire names shared by Engine-owned Benchmarks and Candidate Invocation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

CANDIDATE_ROUTE = "/benchmarks/candidate"
# The source name a client binds its Candidate expression under, so the protocol's `$candidate`
# resolves. Published in every Benchmark resource: a client cannot be expected to infer it.
CANDIDATE_BINDING = "candidate"
CANDIDATE_INPUT_SCHEMA = "screamingface.candidate-input.v1"
CANDIDATE_INVOCATION_SCHEMA = "screamingface.candidate-invocation.v1"
CANDIDATE_RESULT_SCHEMA = "screamingface.candidate-result.v1"
CANDIDATE_MESSAGE_ROLES = frozenset({"system", "developer", "user", "assistant"})
FINISH_REASONS = frozenset({"stop", "length", "tool_calls", "content_filter"})


class CandidateResult(BaseModel):
    """The `screamingface.candidate-result.v1` payload every Benchmark aggregate returns.

    Mental model: this class IS the producer side of the wire contract. An aggregate
    that hand-builds the dict can silently drop a field the SDK renders from (that is
    how an all-pass run once displayed every case as INCORRECT); an aggregate that
    constructs this model cannot — a wrong shape fails in its own unit tests with a
    named validator error. Invariants enforced here, once, instead of as prose in
    three benchmarks:

    - a SCORED result publishes the canonical cross-benchmark trio: `score` plus
      `metrics["pass_rate"]` and `metrics["coverage"]`, each in [0, 1] (draco's
      aggregate is the reference; the SDK report tiles and its low-coverage warning
      read exactly these keys). Per-benchmark metric keys ride alongside — the
      metrics mapping is deliberately open.
    - an UNSCORED result (`score is None`) carries `metrics == {}` — a failed run
      never publishes a plausible partial score.
    - `case_count` is EXACT: one entry per selected Case, scored or failed.

    Check-level MET/UNMET outcomes are pinned by ifeval's tests but not yet enforced
    here: draco's multi-run checks carry verdicts per judge pass and need a roll-up
    design before a single check-level outcome is honest (OME-773 follow-up).
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_version: str = Field(default=CANDIDATE_RESULT_SCHEMA, alias="schema")
    benchmark_id: str
    benchmark_revision: str
    case_count: int = Field(ge=0)
    score: float | None = Field(ge=0.0, le=1.0)
    metrics: dict[str, Any]
    cases: list[dict[str, Any]]
    failures: list[dict[str, Any]]

    @model_validator(mode="after")
    def _enforce_result_contract(self) -> CandidateResult:
        if self.schema_version != CANDIDATE_RESULT_SCHEMA:
            raise ValueError(f"CandidateResult schema must be {CANDIDATE_RESULT_SCHEMA!r}")
        if self.case_count != len(self.cases):
            raise ValueError("case_count must equal the number of retained cases")
        if self.score is None:
            if self.metrics:
                raise ValueError("a failed or unscored Candidate cannot contain metrics")
            return self
        for key in ("pass_rate", "coverage"):
            value = self.metrics.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(
                    f"a scored Candidate must publish canonical metric {key!r} in [0, 1]"
                )
        return self

    def as_payload(self) -> dict[str, Any]:
        """The wire dict — key names, order, and values as the v1 JSON expects."""

        return self.model_dump(by_alias=True)


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
    "CANDIDATE_INPUT_SCHEMA",
    "CANDIDATE_INVOCATION_SCHEMA",
    "CANDIDATE_MESSAGE_ROLES",
    "CANDIDATE_RESULT_SCHEMA",
    "CANDIDATE_ROUTE",
    "FINISH_REASONS",
    "CandidateResult",
    "decode_candidate_invocation",
    "encode_candidate_invocation",
]
