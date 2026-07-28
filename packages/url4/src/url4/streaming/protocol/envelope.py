from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


def source_for(topic: str, node: str | None = None) -> str:
    """The CloudEvents ``source`` URI-ref for a producer: ``/trace/<topic>`` for frames the
    transport itself emits, ``/trace/<topic>/node/<node_id>`` for frames a run node produced.

    Stated once, beside the field it fills — three call sites used to format it by hand and had
    already drifted on whether the ``/node/`` segment was present.
    """
    return f"/trace/{topic}/node/{node}" if node is not None else f"/trace/{topic}"


class CloudEvent(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    specversion: Literal["1.0"] = "1.0"
    id: str
    """Unique per event — the dedup identity (CloudEvents required attribute)."""
    source: str
    """URI-ref of the producer — build it with :func:`source_for`, never by hand."""
    subject: str | None = None
    """The run == ``<trace_id>``."""
    time: datetime | None = None
    datacontenttype: str = "application/json"
    dataschema: str | None = None
    sequence: str | None = None
    sequencetype: Literal["Integer"] | None = None
    traceparent: str | None = None
    tracestate: str | None = None
