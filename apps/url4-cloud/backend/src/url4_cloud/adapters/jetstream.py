"""NATS JetStream adapter for the `EventConsumer`/`EventPublisher` ports
(`url4.streaming.interfaces`): the real, durable telemetry stream a run's frames travel over
between the Runner and the App. Subject and stream names are per-topic, derived by
`url4_cloud.subjects.subject_for`/`stream_for` rather than reimplemented here."""

from collections.abc import AsyncIterator

import nats
from nats.aio.client import Client
from nats.js import JetStreamContext
from nats.js.api import ConsumerConfig, DeliverPolicy
from nats.js.errors import BadRequestError

from url4.streaming.codec import decode, encode
from url4.streaming.interfaces import EventConsumer, EventPublisher, validate_from_sequence
from url4.streaming.protocol import OutboundFrame
from url4_cloud.subjects import stream_for, subject_for


def _consumer_config(from_sequence: int | None) -> ConsumerConfig:
    """Replays from the start of the stream when `from_sequence` is None, else resumes at that
    1-based stream sequence (attach/resume, spec §8)."""
    if from_sequence is None:
        return ConsumerConfig(deliver_policy=DeliverPolicy.ALL)
    return ConsumerConfig(
        deliver_policy=DeliverPolicy.BY_START_SEQUENCE, opt_start_seq=from_sequence
    )


class _JetStreamConnection:
    """One lazily-opened NATS connection and the stream bookkeeping every binding needs.

    Consumer and publisher differ only in which direction they move frames; connecting,
    declaring the stream and closing are the same job, so they are written once here.
    """

    def __init__(self, nats_url: str) -> None:
        self._url = nats_url
        self._nc: Client | None = None
        self._js: JetStreamContext | None = None
        self._ensured: set[str] = set()

    async def _jetstream(self) -> JetStreamContext:
        js = self._js
        if js is None:
            nc = await nats.connect(self._url)
            self._nc = nc
            js = nc.jetstream()
            self._js = js
        return js

    async def ensure_stream(self, topic: str) -> None:
        # WHY: `add_stream` on an existing stream is a round trip that ends in BadRequestError,
        # and every subscribe/attach/publish calls this. One instance owns one connection for
        # its whole life, so what it already declared over that connection stays declared.
        if topic in self._ensured:
            return
        js = await self._jetstream()
        try:
            await js.add_stream(name=stream_for(topic), subjects=[subject_for(topic)])
        except BadRequestError:
            pass
        self._ensured.add(topic)

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.close()


class JetStreamConsumer(_JetStreamConnection, EventConsumer):
    """The App-side consumer: subscribes to a run's JetStream subject and decodes frames back
    into `OutboundFrame`s, optionally resuming from a given sequence."""

    async def subscribe(
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]:
        validate_from_sequence(from_sequence)
        js = await self._jetstream()
        await self.ensure_stream(topic)
        sub = await js.subscribe(
            subject_for(topic),
            stream=stream_for(topic),
            config=_consumer_config(from_sequence),
        )
        # WHY: the caller may abandon this generator mid-run (a re-attach cancels the WS pump, a
        # sync GET gives up at `sync_max_wait_s`). Without the unsubscribe the push consumer keeps
        # delivering into a queue nobody drains, for the life of the connection.
        try:
            async for msg in sub.messages:
                yield decode(msg.data, sequence=msg.metadata.sequence.stream)
        finally:
            await sub.unsubscribe()

    async def purge(self, topic: str) -> None:
        js = await self._jetstream()
        await js.purge_stream(stream_for(topic))


class JetStreamPublisher(_JetStreamConnection, EventPublisher):
    """The App-side publisher. Only the mock runner writes to a topic in a real deployment —
    the real Runner has its own copy, because the two deployables may not import each other."""

    async def publish(self, topic: str, event: OutboundFrame) -> None:
        js = await self._jetstream()
        await js.publish(subject_for(topic), encode(event))


__all__ = ["JetStreamConsumer", "JetStreamPublisher"]
