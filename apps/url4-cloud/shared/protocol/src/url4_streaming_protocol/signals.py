"""Typed CloudEvents ``data`` payloads (docs/protocol.md §5)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from url4_streaming_protocol.taxonomy import CostBreakdown, ErrorInfo, TokenUsage


class StartedData(BaseModel):
    """A node began executing its url4 expression."""

    url4: str


class LogData(BaseModel):
    """OTel Logs Data Model record (docs/protocol.md §5.2)."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    severity_number: int
    """OTel SeverityNumber (DEBUG=5, INFO=9, WARN=13, ERROR=17)."""
    severity_text: Literal["DEBUG", "INFO", "WARN", "ERROR"]
    body: str
    attributes: dict[str, str | int | float | bool | None] = {}


class SpanData(BaseModel):
    """OTel span + GenAI attributes (docs/protocol.md §5.1). Tokens here; cost NOT."""

    model_config = ConfigDict(
        populate_by_name=True, use_attribute_docstrings=True, title="GenAI span"
    )

    name: str
    kind: Literal["client", "internal", "server"] = "internal"
    operation: str = Field(
        validation_alias="gen_ai.operation.name",
        serialization_alias="gen_ai.operation.name",
    )
    provider: str | None = Field(
        default=None,
        validation_alias="gen_ai.provider.name",
        serialization_alias="gen_ai.provider.name",
    )
    request_model: str | None = Field(
        default=None,
        validation_alias="gen_ai.request.model",
        serialization_alias="gen_ai.request.model",
    )
    response_model: str | None = Field(
        default=None,
        validation_alias="gen_ai.response.model",
        serialization_alias="gen_ai.response.model",
    )
    input_tokens: int | None = Field(
        default=None,
        validation_alias="gen_ai.usage.input_tokens",
        serialization_alias="gen_ai.usage.input_tokens",
    )
    output_tokens: int | None = Field(
        default=None,
        validation_alias="gen_ai.usage.output_tokens",
        serialization_alias="gen_ai.usage.output_tokens",
    )
    start: datetime
    end: datetime | None = None
    status: Literal["ok", "error"] = "ok"


class CostUsageData(BaseModel):
    """Cost + token usage — a taxonomy payload, never a span attribute (docs/protocol.md §5.3)."""

    model_config = ConfigDict(
        populate_by_name=True, use_attribute_docstrings=True, title="Cost / usage"
    )

    scope: Literal["self", "subtree"]
    """``self`` = this node only (authoritative); ``subtree`` = self + Σ descendants."""
    provider: str = Field(
        validation_alias="gen_ai.provider.name",
        serialization_alias="gen_ai.provider.name",
    )
    model: str = Field(
        validation_alias="gen_ai.response.model",
        serialization_alias="gen_ai.response.model",
    )
    pricing_version: str
    usage: TokenUsage
    cost: CostBreakdown


class HeartbeatData(BaseModel):
    """Liveness beat (no payload fields)."""


class ResultData(BaseModel):
    """A node's final payload."""

    body: str
    media_type: str | None = None


class TerminatedData(BaseModel):
    """A node reached a terminal state."""

    status: Literal["succeeded", "failed", "stopped", "timed_out"]
    error: ErrorInfo | None = None


class StopData(BaseModel):
    """Request the run stop."""

    reason: str | None = None


class AttachData(BaseModel):
    """Subscribe / resume the stream from a CloudEvents ``sequence``."""

    # INVARIANT: stream sequences are 1-based (docs/protocol.md §6), so a `from_sequence` below 1
    # is a malformed frame, not a legal "start from the beginning" (that is `None`).
    # WHY enforce it here rather than in the bridge: an unbounded value validated cleanly, reached
    # JetStream as `opt_start_seq=0`, was rejected there, and killed the subscription task —
    # which the bridge ran with no done-callback, so the client saw heartbeats forever with no
    # error at all. Rejecting at the protocol edge turns that silence into the existing
    # `invalid_frame` nack (OME-623).
    from_sequence: int | None = Field(default=None, ge=1)


class ErrorData(BaseModel):
    """A rejected/invalid inbound frame — an advisory nack (docs/protocol.md §5)."""

    code: str
    message: str
    ref_id: str | None = None
