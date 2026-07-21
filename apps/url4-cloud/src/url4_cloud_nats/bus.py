"""The ``Bus`` port — an async CloudEvents pub/sub over a per-topic stream (docs/protocol.md §2)."""

from collections.abc import AsyncIterator
from typing import Protocol

from url4_cloud_protocol import OutboundFrame


class Bus(Protocol):
    """Transport-agnostic pub/sub port keyed by capability topic (docs/protocol.md §2, §8).

    - ``ensure_stream(topic)`` — idempotently create the per-topic stream.
    - ``publish(topic, event)`` — append one CloudEvent; the stream assigns its monotonic
      ``sequence`` (docs/protocol.md §6).
    - ``subscribe(topic, from_sequence)`` — async-iterate frames from ``from_sequence``
      (inclusive; ``None`` = from the start), then live.
    - ``purge(topic)`` — drop all buffered frames; the stream sequence keeps counting.
    """

    async def ensure_stream(self, topic: str) -> None: ...
    async def publish(self, topic: str, event: OutboundFrame) -> None: ...
    def subscribe(
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]: ...
    async def purge(self, topic: str) -> None: ...
