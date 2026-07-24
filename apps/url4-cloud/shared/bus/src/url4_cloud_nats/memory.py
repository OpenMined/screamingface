"""``InMemoryBus`` — a headless in-process fake of the JetStream ``Bus`` (docs/protocol.md §2)."""

import asyncio
from collections.abc import AsyncIterator

from url4_cloud_nats.codec import decode, encode
from url4_streaming_protocol import OutboundFrame


class InMemoryBus:
    """In-process ``Bus``: per-topic append log, monotonic sequence, live fan-out to subscribers.

    Mirrors JetStream semantics used by the App/Runner: the stream assigns the CloudEvents
    ``sequence`` (starting at 1), ``subscribe(from_sequence=N)`` replays inclusively then goes
    live, and ``purge`` drops buffered frames while the sequence counter keeps advancing.
    """

    def __init__(self) -> None:
        self._log: dict[str, list[tuple[int, bytes]]] = {}
        self._next_seq: dict[str, int] = {}
        self._conds: dict[str, asyncio.Condition] = {}

    async def ensure_stream(self, topic: str) -> None:
        if topic not in self._log:
            self._log[topic] = []
            # INVARIANT: JetStream stream sequences start at 1 (docs/protocol.md §6).
            self._next_seq[topic] = 1
            self._conds[topic] = asyncio.Condition()

    async def publish(self, topic: str, event: OutboundFrame) -> None:
        await self.ensure_stream(topic)
        cond = self._conds[topic]
        async with cond:
            seq = self._next_seq[topic]
            self._next_seq[topic] = seq + 1
            self._log[topic].append((seq, encode(event)))
            cond.notify_all()

    async def subscribe(
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]:
        await self.ensure_stream(topic)
        cond = self._conds[topic]
        cursor = 1 if from_sequence is None else from_sequence
        while True:
            async with cond:
                # WHY: snapshot ready frames under the lock, then yield outside it — never hold the
                # lock across a yield (a slow consumer would block publishers).
                ready = [(seq, payload) for seq, payload in self._log[topic] if seq >= cursor]
                if not ready:
                    await cond.wait()
                    continue
            for seq, payload in ready:
                cursor = seq + 1
                yield decode(payload, sequence=seq)

    async def purge(self, topic: str) -> None:
        await self.ensure_stream(topic)
        cond = self._conds[topic]
        async with cond:
            # WHY: purge drops buffered frames but the sequence counter is untouched — a replay of a
            # purged sequence returns nothing, matching JetStream purge (docs/protocol.md §6).
            self._log[topic] = []
