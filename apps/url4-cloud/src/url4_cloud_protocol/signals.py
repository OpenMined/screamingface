"""Frame message types — outbound events + inbound commands (spec §7, §7.1)."""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict

from url4_cloud_protocol.envelope import FrameBase
from url4_cloud_protocol.taxonomy import CostBreakdown, ErrorInfo, TokenUsage


# ---- outbound events (engine/tool -> bridge -> client) ----
class Started(FrameBase):
    """A node began executing its url4 expression."""

    type: Literal["started"] = "started"
    url4: str


class Log(FrameBase):
    """A structured log record from a node."""

    type: Literal["log"] = "log"
    level: Literal["debug", "info", "warning", "error"]
    message: str
    fields: dict[str, str | int | float | bool | None] = {}


class Span(FrameBase):
    """An OTel gen_ai span. Token counts live here; cost does NOT (see :class:`CostUsage`)."""

    model_config = ConfigDict(title="GenAI span")

    type: Literal["span"] = "span"
    name: str
    operation: str
    """gen_ai.operation.name, e.g. ``chat``."""
    provider: str | None = None
    request_model: str | None = None
    response_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    start_ts: datetime
    end_ts: datetime | None = None
    status: Literal["ok", "error"] = "ok"


class CostUsage(FrameBase):
    """A single node's cost + token usage — a taxonomy event, never a span attribute."""

    model_config = ConfigDict(
        title="Cost / usage event",
        json_schema_extra={
            "examples": [
                {
                    "type": "cost.usage",
                    "trace_id": "9f2c1e...",
                    "node_id": "root",
                    "seq": 7,
                    "ts": "2026-07-21T09:00:03Z",
                    "scope": "self",
                    "provider": "anthropic",
                    "model": "claude-opus-4-8",
                    "pricing_version": "2026-07-01",
                    "usage": {"input_tokens": 1200, "output_tokens": 340},
                    "cost": {"input_usd": "0.0180", "output_usd": "0.0255", "total_usd": "0.0435"},
                }
            ]
        },
    )

    type: Literal["cost.usage"] = "cost.usage"
    scope: Literal["self", "subtree"]
    """``self`` = this node only (authoritative); ``subtree`` = self + Σ descendants."""
    provider: str
    model: str
    pricing_version: str
    """Pricing table version the USD figures were derived from."""
    usage: TokenUsage
    cost: CostBreakdown


class Heartbeat(FrameBase):
    """Liveness beat from a running node."""

    type: Literal["heartbeat"] = "heartbeat"


class Result(FrameBase):
    """A node's final payload."""

    type: Literal["result"] = "result"
    body: str
    media_type: str | None = None


class Terminated(FrameBase):
    """A node reached a terminal state."""

    type: Literal["terminated"] = "terminated"
    status: Literal["succeeded", "failed", "stopped", "timed_out"]
    error: ErrorInfo | None = None


# ---- inbound commands (client -> bridge -> engine/tool) ----
class Execute(FrameBase):
    """Start the run for this node's url4 expression."""

    type: Literal["execute"] = "execute"
    url4: str
    params: dict[str, str] = {}
    timeout_s: float | None = None


class Stop(FrameBase):
    """Request the run stop."""

    type: Literal["stop"] = "stop"
    reason: str | None = None


class Attach(FrameBase):
    """Subscribe / resume the stream from a given ``seq``."""

    type: Literal["attach"] = "attach"
    from_seq: int | None = None
