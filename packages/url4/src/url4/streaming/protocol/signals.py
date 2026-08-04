from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from url4.streaming.protocol.taxonomy import CostBreakdown, ErrorInfo, TokenUsage


class StartedData(BaseModel):
    url4: str


Severity = Literal["DEBUG", "INFO", "WARN", "ERROR"]

SEVERITY_NUMBER: dict[Severity, int] = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}
"""OTel SeverityNumber per level. The model owns BOTH severity fields, so it owns the mapping
between them too — `LogData(severity_number=9, severity_text="ERROR")` would otherwise validate."""


class LogData(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    severity_number: int
    """OTel SeverityNumber — see :data:`SEVERITY_NUMBER`; use :meth:`at` rather than pairing
    this with `severity_text` by hand."""
    severity_text: Severity
    body: str
    attributes: dict[str, str | int | float | bool | None] = {}

    @classmethod
    def at(
        cls,
        severity: Severity,
        body: str,
        attributes: dict[str, str | int | float | bool | None] | None = None,
    ) -> "LogData":
        """Build a log at `severity`, deriving `severity_number` so the pair cannot disagree."""
        return cls(
            severity_number=SEVERITY_NUMBER[severity],
            severity_text=severity,
            body=body,
            attributes=attributes or {},
        )


class SpanData(BaseModel):
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
    finish_reasons: list[str] | None = Field(
        default=None,
        validation_alias="gen_ai.response.finish_reasons",
        serialization_alias="gen_ai.response.finish_reasons",
    )
    """How each model call on this span ended (`stop` | `length` | `content_filter` |
    `tool_calls`). A LIST because one span can make several calls — a tool-calling turn is
    several round trips — and `None` rather than `[]` when the node made no model call at all,
    which is a different fact from "called a model that reported nothing"."""
    refusal: str | None = Field(default=None)
    """The provider's refusal text, when it sends one. Deliberately NOT a `gen_ai.*` alias:
    OTel has no semantic convention for this field, and inventing one would misrepresent a
    local extension as a standard attribute."""
    start: datetime
    end: datetime | None = None
    status: Literal["ok", "error"] = "ok"


class CostUsageData(BaseModel):
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
    pass


class ResultData(BaseModel):
    body: str
    media_type: str | None = None


class TerminatedData(BaseModel):
    status: Literal["succeeded", "failed", "stopped", "timed_out"]
    error: ErrorInfo | None = None


class StopData(BaseModel):
    reason: str | None = None


class AttachData(BaseModel):
    from_sequence: int | None = Field(default=None, ge=1)


class ErrorData(BaseModel):
    code: str
    message: str
    ref_id: str | None = None
