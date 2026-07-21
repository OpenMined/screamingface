"""Frame envelope — the header every inbound/outbound message carries (spec §7)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FrameBase(BaseModel):
    """Common header for every frame."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    v: int = 1
    """Protocol version."""
    trace_id: str
    """One id per run tree (== the NATS topic / JWT ``sub``)."""
    node_id: str
    """The emitting node."""
    span_id: str | None = None
    parent_span_id: str | None = None
    seq: int = 0
    """Monotonic per outbound stream — the dedup / resume identity."""
    ts: datetime
