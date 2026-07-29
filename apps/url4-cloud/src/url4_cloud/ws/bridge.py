"""Bridges an accepted WebSocket connection to an `EventConsumer` stream and an
optional `JobRunner`, per the `url4.streaming.protocol` wire contract: inbound
attach/stop frames drive (re)subscription and job control, outbound stream
events and heartbeats are multiplexed onto the socket through a single writer.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from url4.streaming.codec import encode
from url4.streaming.interfaces import EventConsumer, JobRunner
from url4.streaming.protocol import (
    AttachEvent,
    ErrorData,
    ErrorEvent,
    HeartbeatEvent,
    InboundFrameAdapter,
    OutboundFrame,
    StopEvent,
    source_for,
)

Clock = Callable[[], datetime]

_InboundEvent = AttachEvent | StopEvent


async def _send(ws: WebSocket, event: OutboundFrame) -> None:
    # WHY: through the codec, not `model_dump_json` — the outbound wire convention is decided
    # in one place, so the WS binding and the NATS binding cannot emit different JSON for one
    # frame.
    await ws.send_text(encode(event).decode())


def _heartbeat(topic: str, clock: Clock) -> HeartbeatEvent:
    return HeartbeatEvent(id=uuid4().hex, source=source_for(topic), subject=topic, time=clock())


def _error(topic: str, clock: Clock, code: str, message: str, ref_id: str | None) -> ErrorEvent:
    return ErrorEvent(
        id=uuid4().hex,
        source=source_for(topic),
        subject=topic,
        time=clock(),
        data=ErrorData(code=code, message=message, ref_id=ref_id),
    )


def _parse_inbound(raw: str) -> _InboundEvent | None:
    """Decode a raw inbound WS text frame into an attach/stop event.

    Returns None (rather than raising) on anything unparseable or failing schema
    validation, so the caller can turn it into an `invalid_frame` error event
    instead of tearing down the connection.
    """
    try:
        return InboundFrameAdapter.validate_json(raw)
    except ValidationError:
        return None


# How many frames may sit undelivered for ONE connection before the pump stops draining the
# stream. Sized to absorb an ordinary burst (a fan-out node finishing many spans at once) without
# letting a stalled reader accumulate a run's entire history in memory.
OUTBOUND_QUEUE_MAX_FRAMES = 1024


class Bridge:
    """Owns the lifecycle of one WS connection: an inbound task that parses attach/stop
    frames and drives (re)subscription to the topic's event stream, and an outbound
    writer that drains a shared queue to the socket, falling back to heartbeats when
    the queue is idle. Either side failing (disconnect, send error) stops the other.
    """

    def __init__(
        self,
        ws: WebSocket,
        stream: EventConsumer,
        topic: str,
        *,
        job_runner: JobRunner | None,
        clock: Clock,
        heartbeat_s: float,
    ) -> None:
        self._ws = ws
        self._stream = stream
        self._topic = topic
        self._job_runner = job_runner
        self._clock = clock
        self._heartbeat_s = heartbeat_s
        # INVARIANT: bounded. `_pump` awaits `put`, so a full queue is BACKPRESSURE — the pump
        # stops draining the stream until the client catches up, instead of buffering the run's
        # whole frame history in this process's heap. An unbounded queue turns one slow or stalled
        # reader (a paused browser tab, a stalled TCP window) into unbounded server memory, and
        # every attached client has its own queue.
        self._out: asyncio.Queue[OutboundFrame] = asyncio.Queue(maxsize=OUTBOUND_QUEUE_MAX_FRAMES)
        self._stop = asyncio.Event()
        self._sub: asyncio.Task[None] | None = None

    def _offer(self, frame: OutboundFrame) -> None:
        """Queue an advisory frame, dropping it if the client is already too far behind.

        WHY dropping is right here and blocking is not: these are nacks and notices produced from
        the inbound task and from a done-callback, neither of which may block. A full queue
        already means the client is not reading, so a nack it would receive 1024 frames from now
        has no value — and `put_nowait` on a BOUNDED queue raises QueueFull, which in a
        done-callback is swallowed and in `_inbound` would tear down the connection.
        """
        try:
            self._out.put_nowait(frame)
        except asyncio.QueueFull:
            pass

    async def run(self) -> None:
        """Run the connection until it ends, then cancel and drain both tasks.

        Blocks for the connection's whole lifetime: either the inbound task
        observes a disconnect or the writer fails to send, and both paths set
        `_stop`, which is the only way this coroutine returns.
        """
        inbound = asyncio.ensure_future(self._inbound())
        writer = asyncio.ensure_future(self._writer())
        try:
            await self._stop.wait()
        finally:
            await self._teardown(inbound, writer)

    async def _inbound(self) -> None:
        # INVARIANT: `_stop` is set in `finally` regardless of how this loop exits, so
        # a client disconnect here always unblocks `run()` and tears down `_writer`.
        try:
            while True:
                event = _parse_inbound(await self._ws.receive_text())
                if event is None:
                    self._offer(
                        _error(
                            self._topic,
                            self._clock,
                            "invalid_frame",
                            "unparseable or invalid inbound frame",
                            None,
                        )
                    )
                    continue
                await self._handle(event)
        except WebSocketDisconnect:
            pass
        finally:
            self._stop.set()

    async def _handle(self, event: _InboundEvent) -> None:
        """Dispatch a validated inbound frame: attach (re)subscribes the stream from
        the given cursor, stop delegates to the job runner if one is configured, or
        else queues an `unsupported` error frame.
        """
        if isinstance(event, AttachEvent):
            self._resubscribe(event.data.from_sequence)
        elif isinstance(event, StopEvent):
            if self._job_runner is not None:
                await self._job_runner.stop(self._topic)
            else:
                self._offer(
                    _error(
                        self._topic,
                        self._clock,
                        "unsupported",
                        "stop not supported: no job runner configured",
                        event.id,
                    )
                )

    def _resubscribe(self, cursor: int | None) -> None:
        # WHY: an attach mid-connection (e.g. client resuming after a gap) replaces
        # the running subscription rather than layering a second one, so at most one
        # pump task is ever forwarding events into `_out`.
        if self._sub is not None:
            self._sub.cancel()
        sub = asyncio.ensure_future(self._pump(cursor))
        sub.add_done_callback(self._on_pump_done)
        self._sub = sub

    def _on_pump_done(self, task: asyncio.Task[None]) -> None:
        # WHY: a cancellation here means `_resubscribe` (or teardown) intentionally
        # replaced/stopped this pump — not a failure — so it is not reported.
        if task.cancelled():
            return
        exc = task.exception()
        if exc is None:
            return
        self._offer(
            _error(
                self._topic,
                self._clock,
                "stream_failed",
                f"the topic subscription failed ({type(exc).__name__}); re-attach to resume",
                None,
            )
        )

    async def _pump(self, cursor: int | None) -> None:
        """Forward stream events for `_topic`, from `cursor` onward, into `_out`."""
        async for event in self._stream.subscribe(self._topic, cursor):
            await self._out.put(event)

    async def _writer(self) -> None:
        try:
            while not self._stop.is_set():
                if not await self._try_send(await self._next()):
                    break
        finally:
            self._stop.set()

    async def _next(self) -> OutboundFrame:
        # WHY: the timeout is what turns an idle `_out` queue into a heartbeat
        # cadence — without it, a quiet topic would leave the socket silent long
        # enough for intermediaries (proxies, load balancers) to consider it dead.
        try:
            return await asyncio.wait_for(self._out.get(), timeout=self._heartbeat_s)
        except TimeoutError:
            return _heartbeat(self._topic, self._clock)

    async def _try_send(self, event: OutboundFrame) -> bool:
        """Send one frame; return False (rather than raising) on disconnect so the
        writer loop can stop cleanly instead of propagating a send error.
        """
        try:
            await _send(self._ws, event)
        except (WebSocketDisconnect, RuntimeError):
            return False
        return True

    async def _teardown(self, *tasks: asyncio.Task[None]) -> None:
        # INVARIANT: the active pump subscription (`_sub`) is always cancelled here
        # alongside the inbound/writer tasks passed in, so `run()` never returns
        # while a subscription is still forwarding events into `_out`.
        pending = [task for task in (self._sub, *tasks) if task is not None]
        for task in pending:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*pending, return_exceptions=True)


async def run_bridge(
    ws: WebSocket,
    stream: EventConsumer,
    topic: str,
    *,
    job_runner: JobRunner | None,
    clock: Clock,
    heartbeat_s: float,
) -> None:
    """Construct a `Bridge` for an already-accepted socket and run it to completion.

    The public entry point for the WS endpoint; blocks until the connection ends
    (client disconnect or an unrecoverable send failure).
    """
    await Bridge(
        ws, stream, topic, job_runner=job_runner, clock=clock, heartbeat_s=heartbeat_s
    ).run()
