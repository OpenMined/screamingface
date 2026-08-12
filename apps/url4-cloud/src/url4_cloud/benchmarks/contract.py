"""Wire names shared by Engine-owned Benchmarks and Candidate Invocation."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

CANDIDATE_ROUTE = "/benchmarks/candidate"
# The source name a client binds its Candidate expression under, so the protocol's `$candidate`
# resolves. Published in every Benchmark resource: a client cannot be expected to infer it.
CANDIDATE_BINDING = "candidate"
CANDIDATE_INPUT_SCHEMA = "screamingface.candidate-input.v1"
CANDIDATE_INVOCATION_SCHEMA = "screamingface.candidate-invocation.v1"
CANDIDATE_RESULT_SCHEMA = "screamingface.candidate-result.v1"
CANDIDATE_MESSAGE_ROLES = frozenset({"system", "developer", "user", "assistant"})
CaseId = StrictInt | StrictStr
Outcome = Literal["MET", "UNMET", "PASS", "FAIL"]
FailureStage = Literal["candidate", "grading", "aggregation"]
CaseStatus = Literal["scored", "refused", "failed"]


class _StrictWireModel(BaseModel):
    """Closed producer value: every structural wire key is intentional."""

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("metadata", "metrics", check_fields=False)
    @classmethod
    def _validate_open_json_mapping(cls, value: object) -> object:
        return _json_value(value)


class EvidenceProducer(_StrictWireModel):
    """The deterministic or model-backed producer of one Evidence item."""

    type: str = Field(min_length=1)
    id: str = Field(min_length=1)


class Evidence(_StrictWireModel):
    """One auditable observation supporting a Check."""

    sequence: int = Field(ge=1)
    producer: EvidenceProducer
    valid: bool
    outcome: Outcome | None = Field(default=None, exclude_if=lambda value: value is None)
    explanation: str | None = Field(default=None, exclude_if=lambda value: value is None)
    raw_output: Any
    metadata: dict[str, Any]

    @field_validator("raw_output")
    @classmethod
    def _validate_raw_output(cls, value: object) -> object:
        return _json_value(value)

    @model_validator(mode="after")
    def _enforce_validity(self) -> Evidence:
        if not self.valid and (self.outcome is not None or self.explanation is not None):
            raise ValueError("invalid Evidence cannot claim an outcome or explanation")
        return self


class Check(_StrictWireModel):
    """One named deterministic or rubric requirement."""

    type: str = Field(min_length=1)
    id: str = Field(min_length=1)
    label: str
    outcome: Literal["MET", "UNMET"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    score: float | None = Field(
        default=None, ge=0.0, le=1.0, exclude_if=lambda value: value is None
    )
    evidence: list[Evidence]
    metadata: dict[str, Any]

    @field_validator("score", mode="before")
    @classmethod
    def _validate_score(cls, value: object) -> object:
        return _finite_score(value)


class CaseGrade(_StrictWireModel):
    """Benchmark-specific grading projected into the shared Case envelope."""

    method: str = Field(min_length=1)
    # HealthBench deliberately permits negative penalty-bearing Case scores.
    score: float | None = Field(le=1.0)
    metrics: dict[str, Any]
    checks: list[Check]

    @field_validator("score", mode="before")
    @classmethod
    def _validate_score(cls, value: object) -> object:
        return _finite_score(value)


class Failure(_StrictWireModel):
    """A bounded public failure attributable to a Case or Candidate."""

    stage: FailureStage
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool | None
    case_id: CaseId | None
    metadata: dict[str, Any]

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: CaseId | None) -> CaseId | None:
        return validate_case_id(value, optional=True)


class CaseResult(_StrictWireModel):
    """One selected Case with an explicit scored, refused, or failed outcome."""

    status: CaseStatus
    case_id: CaseId
    input: str = Field(min_length=1)
    output: str | None
    finish_reason: str | None
    refusal: str | None
    grade: CaseGrade | None
    failures: list[Failure]
    metadata: dict[str, Any]

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: CaseId) -> CaseId:
        validated = validate_case_id(value)
        assert validated is not None
        return validated

    @field_validator("refusal")
    @classmethod
    def _validate_refusal(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("refusal must be non-empty text or null")
        return value

    @field_validator("finish_reason")
    @classmethod
    def _validate_finish_reason(cls, value: str | None) -> str | None:
        return validate_finish_reason(value)

    @model_validator(mode="after")
    def _enforce_status(self) -> CaseResult:
        if any(failure.case_id != self.case_id for failure in self.failures):
            raise ValueError("every Case Failure must reference its own case_id")
        if self.status == "scored":
            if (
                self.grade is None
                or self.grade.score is None
                or self.output is None
                or self.refusal is not None
                or self.failures
            ):
                raise ValueError(
                    "a scored Case requires output and a numeric grade and cannot carry refusal "
                    "or failures"
                )
            return self
        if self.status == "refused":
            refusal_failures = [
                failure
                for failure in self.failures
                if failure.stage == "candidate" and failure.code == "provider_refusal"
            ]
            if (
                self.refusal is None
                or self.output is not None
                or self.grade is not None
                or len(self.failures) != 1
                or len(refusal_failures) != 1
            ):
                raise ValueError(
                    "a refused Case requires exact refusal text, no output or grade, and one "
                    "candidate provider_refusal Failure"
                )
            return self
        if (
            not self.failures
            or self.refusal is not None
            or any(failure.code == "provider_refusal" for failure in self.failures)
            or self.grade is not None
            and self.grade.score is not None
        ):
            raise ValueError("a failed Case requires failures, no refusal, and no numeric grade")
        return self


class CandidateResult(_StrictWireModel):
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

    model_config = ConfigDict(populate_by_name=True, extra="forbid", strict=True)

    schema_version: str = Field(default=CANDIDATE_RESULT_SCHEMA, alias="schema")
    benchmark_id: str
    benchmark_revision: str
    case_count: int = Field(ge=0)
    # WHY no lower bound: draco and ifeval scores live in [0, 1], but healthbench's
    # challenge metric is an UNCLIPPED mean over penalty-carrying rubrics — negative
    # scores are meaningful and rankable (clamping here would corrupt the metric).
    # The canonical trio metrics (pass_rate, coverage) stay [0, 1] regardless.
    score: float | None = Field(le=1.0)
    metrics: dict[str, Any]
    cases: list[CaseResult]
    failures: list[Failure]

    @field_validator("score", mode="before")
    @classmethod
    def _validate_score(cls, value: object) -> object:
        return _finite_score(value)

    @model_validator(mode="after")
    def _enforce_result_contract(self) -> CandidateResult:
        if self.schema_version != CANDIDATE_RESULT_SCHEMA:
            raise ValueError(f"CandidateResult schema must be {CANDIDATE_RESULT_SCHEMA!r}")
        if self.case_count != len(self.cases):
            raise ValueError("case_count must equal the number of retained cases")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("CandidateResult cannot contain duplicate case_id values")
        if any(failure.case_id is not None for failure in self.failures):
            raise ValueError("a Candidate-level Failure cannot claim a case_id")
        _candidate_outcome(self)
        return self

    def as_payload(self) -> dict[str, Any]:
        """The wire dict — key names, order, and values as the v1 JSON expects."""

        return self.model_dump(by_alias=True)


def _canonical_metrics(metrics: Mapping[str, Any]) -> None:
    """Validate the two cross-Benchmark scored-result metrics."""

    for key in ("pass_rate", "coverage"):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float) or not 0.0 <= value <= 1.0:
            raise ValueError(f"a scored Candidate must publish canonical metric {key!r} in [0, 1]")


def _candidate_outcome(result: CandidateResult) -> None:
    if result.score is None:
        if result.metrics:
            raise ValueError("a failed or unscored Candidate cannot contain metrics")
        if not result.failures and all(case.status == "scored" for case in result.cases):
            raise ValueError(
                "an unscored Candidate must be explained by a non-scored Case or Failure"
            )
        return
    if result.failures or any(case.status != "scored" for case in result.cases):
        raise ValueError("a scored Candidate cannot contain a non-scored Case or failure")
    _canonical_metrics(result.metrics)


def validate_case_id(value: CaseId | None, *, optional: bool = False) -> CaseId | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError("case_id must be a non-boolean integer or non-blank string")
    if isinstance(value, str) and not value.strip():
        raise ValueError("case_id must be a non-boolean integer or non-blank string")
    return value


def validate_finish_reason(value: object) -> str | None:
    """Preserve any non-blank provider finish reason without freezing its vocabulary."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("finish_reason must be non-empty provider text or null")
    return value


def _json_value(value: object) -> object:
    if not _is_json_value(value):
        raise ValueError("open wire fields must contain JSON values")
    return value


def _is_json_value(value: object) -> bool:
    value_type = type(value)
    valid = value is None or value_type in {str, bool, int}
    if value_type is float:
        valid = math.isfinite(cast(float, value))
    elif value_type is list:
        valid = all(_is_json_value(item) for item in cast(list[object], value))
    elif value_type is dict:
        valid = all(
            type(key) is str and _is_json_value(item)
            for key, item in cast(dict[object, object], value).items()
        )
    return valid


def _finite_score(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("score must be a finite number or null")
    if isinstance(value, int | float) and not math.isfinite(value):
        raise ValueError("score must be a finite number or null")
    return value


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
    validate_finish_reason(finish_reason)
    if refusal is not None and (not isinstance(refusal, str) or not refusal.strip()):
        raise ValueError("Candidate Invocation refusal must be non-empty text or null")


__all__ = [
    "CANDIDATE_BINDING",
    "CANDIDATE_INPUT_SCHEMA",
    "CANDIDATE_INVOCATION_SCHEMA",
    "CANDIDATE_MESSAGE_ROLES",
    "CANDIDATE_RESULT_SCHEMA",
    "CANDIDATE_ROUTE",
    "CaseId",
    "CaseGrade",
    "CaseResult",
    "CandidateResult",
    "Check",
    "Evidence",
    "EvidenceProducer",
    "Failure",
    "decode_candidate_invocation",
    "encode_candidate_invocation",
    "validate_case_id",
    "validate_finish_reason",
]
