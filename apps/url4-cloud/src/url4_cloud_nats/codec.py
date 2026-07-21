"""Wire codec + NATS subject/stream naming for the CloudEvents bus (docs/protocol.md §1, §8)."""

import json
from typing import Any

from url4_streaming_protocol import OutboundFrame, OutboundFrameAdapter

# WHY: one JetStream stream + one subject per capability topic (docs/protocol.md §2.1, §8). The
# stream name and subject derive deterministically from the topic so App and Runner agree.
_PREFIX = "url4-cloud"


def subject_for(topic: str) -> str:
    """CloudEvents NATS-binding subject carrying a topic's frames."""
    return f"{_PREFIX}.{topic}"


def stream_for(topic: str) -> str:
    """JetStream stream name backing a topic (stream names forbid ``.``)."""
    return f"{_PREFIX}_{topic}"


def encode(event: OutboundFrame) -> bytes:
    # INVARIANT: serialize per protocol — gen_ai.* aliases + CloudEvents shape (docs §1).
    return json.dumps(event.model_dump(mode="json", by_alias=True)).encode()


def decode(payload: bytes, sequence: int | None = None) -> OutboundFrame:
    # WHY: the stream assigns the authoritative CloudEvents ``sequence`` (docs/protocol.md §6);
    # inject it on read so every subscriber sees a monotonic, stream-truthful sequence regardless
    # of what (if anything) the publisher set.
    obj: dict[str, Any] = json.loads(payload)
    if sequence is not None:
        obj["sequence"] = str(sequence)
        obj["sequencetype"] = "Integer"
    return OutboundFrameAdapter.validate_python(obj)
