from __future__ import annotations

import asyncio

from url4.streaming.interfaces import EventConsumer
from url4.streaming.protocol import OutboundFrame

TAKE_TIMEOUT_S = 2.0


async def take(
    stream: EventConsumer,
    topic: str,
    n: int,
    from_sequence: int | None = None,
    *,
    timeout_s: float = TAKE_TIMEOUT_S,
) -> list[OutboundFrame]:
    got: list[OutboundFrame] = []

    async def _drain() -> None:
        async for event in stream.subscribe(topic, from_sequence):
            got.append(event)
            if len(got) >= n:
                return

    await asyncio.wait_for(_drain(), timeout=timeout_s)
    return got


__all__ = ["TAKE_TIMEOUT_S", "take"]
