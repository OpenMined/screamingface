"""NATS JetStream adapter for the `EventConsumer`/`EventPublisher` ports
(`url4.streaming.interfaces`): the real, durable telemetry stream a run's frames travel over
between the Runner and the App. Subject and stream names are per-topic, derived by
`url4_cloud.subjects.subject_for`/`stream_for` rather than reimplemented here."""

import asyncio
from collections.abc import AsyncIterator

import nats
from nats.aio.client import Client
from nats.js import JetStreamContext
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, DiscardPolicy
from nats.js.errors import BadRequestError, NotFoundError

from url4.streaming.codec import decode, encode
from url4.streaming.interfaces import EventConsumer, EventPublisher, validate_from_sequence
from url4.streaming.protocol import OutboundFrame
from url4_cloud.subjects import stream_for, subject_for

# INVARIANT: a run's stream must outlive the run itself plus the window in which a client may
# still attach and replay it. This is the ceiling for BOTH, and it is what stops an abandoned
# run's frames from sitting in the filestore forever: `purge` deletes the stream on the normal
# DELETE path, and `max_age` reclaims the ones no client ever gets around to deleting.
DEFAULT_STREAM_MAX_AGE_S = 86_400.0
# INVARIANT: bytes retained per run. JetStream's own default is unlimited, which makes one
# runaway expression enough to fill the NATS filestore and take down every other run with it.
DEFAULT_STREAM_MAX_BYTES = 256 * 1024 * 1024
# WHY bound the memo: it exists only to skip a round trip, so forgetting an entry costs one
# `add_stream` call. Left unbounded it is a per-topic set that grows for the process's lifetime.
_MAX_ENSURED_MEMO = 4096


def _consumer_config(from_sequence: int | None) -> ConsumerConfig:
    """Replays from the start of the stream when `from_sequence` is None, else resumes at that
    1-based stream sequence (attach/resume, spec §8).

    INVARIANT: `ack_policy` is NONE, and this is load-bearing rather than a default worth
    inheriting. These consumers are broadcast replay readers — nothing here can act on a
    redelivery, and the subscription is torn down and rebuilt from a sequence on re-attach, so
    acks buy nothing. Under the EXPLICIT default, `subscribe()` without a callback never acks
    anything (nats-py only auto-acks the callback path), which means every frame is redelivered
    after AckWait and delivery stops outright once `max_ack_pending` (server default 1000)
    unacked messages pile up — i.e. any run over ~1000 frames silently truncates mid-stream.
    """
    if from_sequence is None:
        return ConsumerConfig(deliver_policy=DeliverPolicy.ALL, ack_policy=AckPolicy.NONE)
    return ConsumerConfig(
        deliver_policy=DeliverPolicy.BY_START_SEQUENCE,
        opt_start_seq=from_sequence,
        ack_policy=AckPolicy.NONE,
    )


class _JetStreamConnection:
    """One lazily-opened NATS connection and the stream bookkeeping every binding needs.

    Consumer and publisher differ only in which direction they move frames; connecting,
    declaring the stream and closing are the same job, so they are written once here.
    """

    def __init__(
        self,
        nats_url: str,
        *,
        stream_max_age_s: float = DEFAULT_STREAM_MAX_AGE_S,
        stream_max_bytes: int = DEFAULT_STREAM_MAX_BYTES,
    ) -> None:
        self._url = nats_url
        self._stream_max_age_s = stream_max_age_s
        self._stream_max_bytes = stream_max_bytes
        self._nc: Client | None = None
        self._js: JetStreamContext | None = None
        self._ensured: set[str] = set()
        self._connect_lock = asyncio.Lock()

    async def _jetstream(self) -> JetStreamContext:
        # WHY the lock and the second check inside it: `subscribe`/`publish` are called
        # concurrently (one WS pump per attached client, plus the sync-hold GET). Without it two
        # callers both observe `_js is None`, both connect, and one `Client` is overwritten while
        # still open — leaking its reader task and TLS pool for the life of the process, once per
        # racing pair. Re-checking under the lock is what makes the second caller reuse the first
        # connection instead of opening its own.
        js = self._js
        if js is not None and not self._is_closed():
            return js
        async with self._connect_lock:
            js = self._js
            if js is not None and not self._is_closed():
                return js
            nc = await nats.connect(self._url)
            self._nc = nc
            js = nc.jetstream()
            self._js = js
            # The declarations belonged to the connection that just died; the new one has none.
            self._ensured.clear()
            return js

    def _is_closed(self) -> bool:
        """Whether the cached connection is known-dead and must be rebuilt.

        WHY this exists: nats-py gives up after its reconnect budget is exhausted, and a handle
        cached for the process lifetime would fail every subsequent call with no path back. The
        control plane outlives any single NATS outage, so it has to be able to reconnect.

        A missing `_nc` is NOT closed: a `JetStreamContext` can be supplied without one going
        through `nats.connect` here, and treating that as dead would discard a perfectly live
        context and dial the broker instead.
        """
        nc = self._nc
        return nc is not None and nc.is_closed

    async def ensure_stream(self, topic: str) -> None:
        # WHY: `add_stream` on an existing stream is a round trip that ends in BadRequestError,
        # and every subscribe/attach/publish calls this. One instance owns one connection for
        # its whole life, so what it already declared over that connection stays declared.
        if topic in self._ensured:
            return
        js = await self._jetstream()
        try:
            await js.add_stream(
                name=stream_for(topic),
                subjects=[subject_for(topic)],
                max_age=self._stream_max_age_s,
                max_bytes=self._stream_max_bytes,
                discard=DiscardPolicy.OLD,
            )
        except BadRequestError:
            pass
        if len(self._ensured) >= _MAX_ENSURED_MEMO:
            self._ensured.clear()
        self._ensured.add(topic)

    async def delete_stream(self, topic: str) -> None:
        """Drop a run's stream entirely, tolerating one that is already gone.

        INVARIANT: this is the only thing that reclaims a stream OBJECT. `purge_stream` empties a
        stream but leaves it, its consumer state and its filestore directory behind, so a
        purge-only teardown still adds one permanent stream to the NATS metaleader per run.
        """
        js = await self._jetstream()
        try:
            await js.delete_stream(stream_for(topic))
        except NotFoundError:
            pass
        self._ensured.discard(topic)

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
        # Idempotent by contract: `InMemoryEventStream.purge` creates-then-empties an unknown
        # topic and returns, so purging one that was never published to must not raise here
        # either. Without the guard `purge_stream` raises NotFoundError and the DELETE route
        # turns a 204 into a 500 — a divergence only a real broker would ever show.
        js = await self._jetstream()
        try:
            await js.purge_stream(stream_for(topic))
        except NotFoundError:
            pass


class JetStreamPublisher(_JetStreamConnection, EventPublisher):
    """The App-side publisher. Only the mock runner writes to a topic in a real deployment —
    the real Runner has its own copy, because the two deployables may not import each other."""

    async def publish(self, topic: str, event: OutboundFrame) -> None:
        js = await self._jetstream()
        await js.publish(subject_for(topic), encode(event))


__all__ = ["JetStreamConsumer", "JetStreamPublisher"]
