"""CloudEvents 1.0 envelope (structured mode) — the base for every message (docs/protocol.md §1)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CloudEvent(BaseModel):
    """A CloudEvents 1.0 event; subclasses fix ``type`` + ``data`` (docs/protocol.md §4)."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    specversion: Literal["1.0"] = "1.0"
    id: str
    """Unique per event — the dedup identity (CloudEvents required attribute)."""
    source: str
    """URI-ref of the producer, e.g. ``/trace/<trace_id>/node/<node_id>``."""
    subject: str | None = None
    """The run == ``<trace_id>``."""
    time: datetime | None = None
    datacontenttype: str = "application/json"
    dataschema: str | None = None
    # CloudEvents Sequence extension (docs/protocol.md §6).
    sequence: str | None = None
    sequencetype: Literal["Integer"] | None = None
    # CloudEvents Distributed Tracing extension — W3C traceparent (docs/protocol.md §3).
    traceparent: str | None = None
    tracestate: str | None = None
