"""``NatsBus`` — the ``Bus`` over NATS JetStream, CloudEvents NATS binding (docs/protocol.md §8).

Real-infra adapter: one JetStream stream per capability topic, the server-assigned stream
sequence is the CloudEvents ``sequence`` (docs/protocol.md §6). Live NATS I/O is exercised by the
compose e2e (OME-524), not by headless unit tests (INFRA rule) — the pure codec/naming logic it
shares with ``InMemoryBus`` is covered there.
"""

from collections.abc import AsyncIterator

import nats
from nats.aio.client import Client
from nats.js import JetStreamContext
from nats.js.api import ConsumerConfig, DeliverPolicy
from nats.js.errors import BadRequestError

from url4_cloud_nats.codec import decode, encode, stream_for, subject_for
from url4_cloud_protocol import OutboundFrame


def _consumer_config(from_sequence: int | None) -> ConsumerConfig:
    if from_sequence is None:
        return ConsumerConfig(deliver_policy=DeliverPolicy.ALL)
    # WHY: BY_START_SEQUENCE is inclusive — replays the gap from ``from_sequence`` (docs §6).
    return ConsumerConfig(
        deliver_policy=DeliverPolicy.BY_START_SEQUENCE, opt_start_seq=from_sequence
    )


class NatsBus:
    """``Bus`` backed by NATS JetStream; connects lazily on first use."""

    def __init__(self, nats_url: str) -> None:
        self._url = nats_url
        self._nc: Client | None = None
        self._js: JetStreamContext | None = None

    async def _jetstream(self) -> JetStreamContext:
        js = self._js
        if js is None:
            self._nc = await nats.connect(self._url)
            js = self._nc.jetstream()
            self._js = js
        return js

    async def ensure_stream(self, topic: str) -> None:
        js = await self._jetstream()
        try:
            await js.add_stream(name=stream_for(topic), subjects=[subject_for(topic)])
        except BadRequestError:
            # WHY: idempotent ensure — the stream already exists; reuse it.
            pass

    async def publish(self, topic: str, event: OutboundFrame) -> None:
        js = await self._jetstream()
        await js.publish(subject_for(topic), encode(event))

    async def subscribe(
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]:
        js = await self._jetstream()
        sub = await js.subscribe(
            subject_for(topic),
            stream=stream_for(topic),
            config=_consumer_config(from_sequence),
        )
        async for msg in sub.messages:
            yield decode(msg.data, sequence=msg.metadata.sequence.stream)

    async def purge(self, topic: str) -> None:
        js = await self._jetstream()
        await js.purge_stream(stream_for(topic))

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.close()
