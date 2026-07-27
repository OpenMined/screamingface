"""The ``Bus`` port — an async CloudEvents pub/sub over a per-topic stream (docs/protocol.md §2)."""

from collections.abc import AsyncIterator
from typing import Protocol

from url4_streaming_protocol import OutboundFrame


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


def validate_from_sequence(from_sequence: int | None) -> None:
    """Reject a ``from_sequence`` below 1 — every :class:`Bus` adapter must agree here.

    INVARIANT: stream sequences are 1-based (docs/protocol.md §6); ``None`` means "from the
    start". Anything below 1 is a caller error.

    WHY this lives on the port rather than in each adapter: the two implementations silently
    DISAGREED. ``InMemoryBus`` filtered ``seq >= from_sequence``, so 0 matched everything and
    replayed the whole stream, while JetStream rejects ``opt_start_seq=0`` outright. The double
    was more permissive than production, so the unit suite could not catch a real hang (OME-623).
    One shared guard keeps the contract honest in both.
    """
    if from_sequence is not None and from_sequence < 1:
        raise ValueError(
            f"from_sequence must be >= 1 (1-based stream sequence), got {from_sequence}"
        )
