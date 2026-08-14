from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

# INVARIANT: a baseline's metadata is operator-supplied (via the import CLI, not a
# public HTTP endpoint) but still bounded, so one bad import can't make
# GET /v1/leaderboard/{id} fail to serialize for every consumer (found in PR review).
_METADATA_MAX_DEPTH = 4
_METADATA_MAX_BYTES = 4096


def _metadata_depth(value: object, current: int = 0) -> int:
    if isinstance(value, dict):
        return max((_metadata_depth(v, current + 1) for v in value.values()), default=current)
    if isinstance(value, list):
        return max((_metadata_depth(v, current + 1) for v in value), default=current)
    return current


def _validate_bounded_metadata(value: dict[str, Any] | None) -> dict[str, Any] | None:
    # WHY: shared by both the import DTO and the read schema — a bad row must never
    # reach storage in the first place, but bounding the read side too means the
    # invariant holds regardless of how a row got into the database (found in PR
    # review: metadata was previously bounded on import only).
    if value is None:
        return value
    if _metadata_depth(value) > _METADATA_MAX_DEPTH:
        raise ValueError(f"metadata must not be nested past {_METADATA_MAX_DEPTH} levels deep")
    if len(json.dumps(value)) > _METADATA_MAX_BYTES:
        raise ValueError(f"metadata must serialize to at most {_METADATA_MAX_BYTES} bytes")
    return value


def _publish_submitter(value: str | None) -> str | None:
    """Publish the local part of an email, never the domain.

    WHY: since OME-404 this field holds the mesh-verified address from the Cloudflare
    Access identity header, and the read API is PUBLIC and unauthenticated — a
    harvester can pull every submitter's address straight out of
    `GET /v1/leaderboard/{id}`. Stripping in the portal would have looked correct
    while leaving the JSON exposed, so the trim lives here, where every consumer
    (portal, SDK notebook view, anything future) is served from one place.

    INVARIANT: this is a SERIALIZER, not a validator. The stored value keeps its
    domain so OpenMined can still contact a submitter and audit which verified
    identity produced a score. Do NOT move this onto ScoreSubmission — that carries
    the value inbound, and trimming there would write the truncated form to the
    database irreversibly.

    AIDEV-NOTE: this is a stopgap, not privacy. `filip.boltuzic` still names a
    person, `first.last@domain` is trivially reconstructed, and
    trask@openmined.org and trask@gmail.com both render `trask` — two testers on
    different domains become indistinguishable on a board that attributes credit.
    A real username field is the fix; OME-772 records that none exists (OME-834).
    """
    # Only trim something that actually looks like ONE address. Anything else is free
    # text that happens to contain "@", and truncating it loses meaning. Gating on the
    # bare presence of "@" was the original bug (OME-834 review):
    #   " @openmined.org"     -> " "        a BLANK submitter, not an empty one, so a
    #                                       `local or value` guard did not catch it —
    #                                       and the SDK's _text rejects blank-after-
    #                                       strip, raising LeaderboardError for the
    #                                       WHOLE board off one poisoned row.
    #   "Team A @ OpenMined"  -> "Team A "  free text silently truncated.
    if value is None or "@" not in value or any(char.isspace() for char in value):
        return value
    local, _, domain = value.rpartition("@")
    # A public address needs a non-blank local part and a dotted domain. `user@github`
    # is a handle, not an address, so it passes through untouched.
    return local if local.strip() and "." in domain else value


# INVARIANT: the ONE definition of how a submitter reaches a client, shared by every
# read DTO so the four cannot drift. `when_used="json"` is deliberate — _ranked_entry
# splats entry.model_dump() in PYTHON mode and must keep receiving the stored value.
SubmittedBy = Annotated[
    str | None,
    PlainSerializer(_publish_submitter, return_type=str | None, when_used="json"),
]


class ClientInfo(BaseModel):
    """Optional client metadata for a score submission."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    version: str | None = None
    platform: str | None = None


class FieldErrorDetail(BaseModel):
    """Field-specific HTTP error detail."""

    model_config = ConfigDict(extra="forbid")

    field: str
    message: str


class FieldErrorResponse(BaseModel):
    """HTTP error response for errors tied to a request field."""

    model_config = ConfigDict(extra="forbid")

    detail: FieldErrorDetail


class MessageErrorResponse(BaseModel):
    """HTTP error response with a flat detail message."""

    model_config = ConfigDict(extra="forbid")

    detail: str


class ScoreSubmission(BaseModel):
    """Input DTO for score ingestion."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    benchmark_id: str
    # WHY optional: the deployed Client sends this nested in `metadata` rather than as a typed
    # field, so the store resolves either shape (_resolve_benchmark_revision). Requiring it
    # here would 422 every submission in the field; see OME-775 D5.
    benchmark_revision: str | None = None
    spec_id: str
    url4_expression: Annotated[str, Field(max_length=32_000)]
    submitted_by: str | None = None
    accuracy: float
    total_questions: int
    correct_questions: int
    ran_with_providers: list[str]
    ran_at_local: datetime | None = None
    # Nested client metadata, matching the SF "Publish to Leaderboard" wire shape
    # (D-SCORE-006). Persisted onto the flat client_* columns by the store.
    client: ClientInfo | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("url4_expression")
    @classmethod
    def validate_url4_expression(cls, value: str) -> str:
        if not value:
            raise ValueError("url4_expression must be non-empty")
        return value

    @field_validator("benchmark_id", "spec_id")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        if not value:
            raise ValueError("identifier fields must be non-empty")
        return value

    @field_validator("accuracy")
    @classmethod
    def validate_accuracy(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("accuracy must be between 0 and 1")
        return value

    @field_validator("total_questions")
    @classmethod
    def validate_total_questions(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("total_questions must be positive")
        return value

    @field_validator("correct_questions")
    @classmethod
    def validate_correct_questions(cls, value: int) -> int:
        if value < 0:
            raise ValueError("correct_questions must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_questions(self) -> ScoreSubmission:
        if self.correct_questions > self.total_questions:
            raise ValueError("correct_questions cannot exceed total_questions")
        return self


class BenchmarkSchema(BaseModel):
    """Read DTO for benchmarks."""

    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    description: str | None
    dataset_url: str | None
    # WHY exposed: a client comparing its run against the board needs to know which revision
    # the board is registered at, so it can tell a real score gap from an incomparable one.
    revision: str | None
    created_at: datetime


class ScoreSchema(BaseModel):
    """Read DTO for a score."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    version: int
    benchmark_id: str
    # WHY: the Engine benchmark revision this score was measured against, resolved from either
    # wire shape by the store. Null for imported baselines and rows predating OME-775.
    benchmark_revision: str | None
    spec_id: str
    url4_expression: str
    submitted_by: SubmittedBy
    submitted_at: datetime
    accuracy: float
    total_questions: int
    correct_questions: int
    ran_with_providers: list[str]
    ran_at_local: datetime | None
    client_name: str | None
    client_version: str | None
    client_platform: str | None
    verified_by_openmined: bool
    metadata: dict[str, Any] | None
    # FEATURE: OME-323 — manual open/closed correction; None defers to the
    # classification registry. Operator-only, never set via ScoreSubmission.
    openness_override: Literal["open", "closed"] | None = None


class LeaderboardEntry(BaseModel):
    """Read DTO for a leaderboard row before route rank assignment."""

    model_config = ConfigDict(extra="forbid")

    spec_id: str
    # WHY exposed: the board partitions ranking on this, so a client seeing two rows for one
    # spec needs the revision to know why they are not competing (OME-775). Null for rows that
    # predate the column and for imported baselines.
    benchmark_revision: str | None
    accuracy: float
    total_questions: int
    ran_with_providers: list[str]
    submitted_at: datetime
    submitted_by: SubmittedBy
    verified_by_openmined: bool
    url4_expression: str


class BaselineSchema(BaseModel):
    """Read DTO for an imported single-model baseline ('line to beat')."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    benchmark_id: str
    model_name: str
    accuracy: float
    source: str
    source_url: str | None
    imported_at: datetime
    metadata: dict[str, Any] | None
    # FEATURE: OME-323 — manual open/closed correction, mirrors ScoreSchema's field.
    openness_override: Literal["open", "closed"] | None = None

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_bounded_metadata(value)


class FrontierPoint(BaseModel):
    """One step of the open/closed frontier trend (OME-323, spec §5/§6): the
    running-best accuracy at the moment it changed, and whether the entry holding
    that position was open or closed."""

    model_config = ConfigDict(extra="forbid")

    at: datetime
    accuracy: float
    openness: Literal["open", "closed"]
    # INVARIANT: always "score" — a Baseline's imported_at isn't a trustworthy
    # real-world timestamp, so it never participates in this walk (spec §6).
    holder: Literal["score"]
    label: str


class FrontierResult(BaseModel):
    """Return type of `compute_frontier` — no `benchmark_id`, since the pure
    function itself has no notion of which benchmark it was called for. The route
    adds that to build the public `FrontierResponse`."""

    model_config = ConfigDict(extra="forbid")

    open_count: int
    closed_count: int
    open_share: float
    current: FrontierPoint | None
    trend: list[FrontierPoint]


class FrontierResponse(BaseModel):
    """Read DTO for GET /v1/leaderboard/{benchmark_id}/frontier (OME-323, spec §5)."""

    model_config = ConfigDict(extra="forbid")

    benchmark_id: str
    open_count: int
    closed_count: int
    open_share: float
    current: FrontierPoint | None
    trend: list[FrontierPoint]


class BaselineImportRow(BaseModel):
    """Input DTO for importing a single-model baseline score (e.g. from LMArena /
    Artificial Analysis). Re-importing the same (benchmark_id, model_name, source)
    updates the existing row rather than duplicating it (see BaselineStore).
    """

    model_config = ConfigDict(extra="forbid")

    benchmark_id: str
    model_name: str
    # WHY: strict + no-inf-nan closes a Pydantic v2 laziness gap where JSON true/false
    # coerce to 1.0/0.0 and numeric strings coerce to float, letting malformed source
    # data silently become a plausible-looking score (found in PR review). The range
    # check stays a separate validator below so its error message doesn't change for
    # an existing test.
    accuracy: Annotated[float, Field(strict=True, allow_inf_nan=False)]
    source: str
    # WHY: this is returned through the public API and a future client will likely
    # render it as a link — restrict to http(s) so a javascript:/data: URI can't
    # become an XSS vector downstream (found in PR review).
    source_url: Annotated[str, Field(max_length=2048)] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("benchmark_id", "model_name", "source")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        if not value:
            raise ValueError("identifier fields must be non-empty")
        return value

    @field_validator("accuracy")
    @classmethod
    def validate_accuracy(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("accuracy must be between 0 and 1")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("source_url must start with http:// or https://")
        return value

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_bounded_metadata(value)
