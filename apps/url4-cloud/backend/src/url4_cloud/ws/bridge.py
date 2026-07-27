"""The ``Bus`` → WebSocket streaming engine (spec §6; docs/protocol.md §8).

One CloudEvent per WS message (structured mode). Three cooperating pieces on the app's event loop:

- **subscription task** — ``Bus.subscribe(topic, cursor)`` feeding an outbound queue; (re)started
  from an inbound ``Attach`` so a reconnecting client resumes from ``from_sequence`` (spec §6).
- **writer** — the *sole* sender: drains the queue, and on idle (``ws_heartbeat_s`` elapsed) emits a
  ``HeartbeatEvent`` for liveness. Single sender ⇒ no interleaved WS writes, no lock.
- **inbound** — reads client frames; ``Attach`` re-subscribes, ``Stop`` calls ``JobRunner.stop``.

The bridge ends when the client disconnects (inbound raises ``WebSocketDisconnect``) or a send
fails; either sets the stop event and the rest is cancelled.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from url4_cloud.jobs.port import JobRunner
from url4_cloud_nats import Bus
from url4_streaming_protocol import (
    AttachEvent,
    ErrorData,
    ErrorEvent,
    HeartbeatEvent,
    InboundFrameAdapter,
    OutboundFrame,
    StopEvent,
)

Clock = Callable[[], datetime]

_InboundEvent = AttachEvent | StopEvent


async def _send(ws: WebSocket, event: OutboundFrame) -> None:
    # INVARIANT: serialize per protocol.md §1 — by_alias yields the gen_ai.* + CloudEvents shape.
    await ws.send_json(event.model_dump(mode="json", by_alias=True))


def _heartbeat(topic: str, clock: Clock) -> HeartbeatEvent:
    return HeartbeatEvent(id=uuid4().hex, source=f"/trace/{topic}", subject=topic, time=clock())


def _error(topic: str, clock: Clock, code: str, message: str, ref_id: str | None) -> ErrorEvent:
    # WHY: an advisory nack for a rejected inbound frame — an outbound OutboundFrame the inbound
    # task *enqueues* (never sends), so the writer stays the sole ws.send caller (single-writer).
    return ErrorEvent(
        id=uuid4().hex,
        source=f"/trace/{topic}",
        subject=topic,
        time=clock(),
        data=ErrorData(code=code, message=message, ref_id=ref_id),
    )


def _parse_inbound(raw: str) -> _InboundEvent | None:
    # WHY: tolerate malformed client frames — ignore rather than tear down the stream.
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    try:
        return InboundFrameAdapter.validate_python(obj)
    except ValidationError:
        return None


class Bridge:
    """Bridges one topic's ``Bus`` stream to one WebSocket for the life of the connection."""

    def __init__(
        self,
        ws: WebSocket,
        bus: Bus,
        topic: str,
        *,
        job_runner: JobRunner | None,
        clock: Clock,
        heartbeat_s: float,
    ) -> None:
        self._ws = ws
        self._bus = bus
        self._topic = topic
        self._job_runner = job_runner
        self._clock = clock
        self._heartbeat_s = heartbeat_s
        self._out: asyncio.Queue[OutboundFrame] = asyncio.Queue()
        self._stop = asyncio.Event()
        self._sub: asyncio.Task[None] | None = None

    async def run(self) -> None:
        inbound = asyncio.ensure_future(self._inbound())
        writer = asyncio.ensure_future(self._writer())
        # WHY: teardown in a finally so it also runs when the ASGI task is *cancelled* (the
        # TestClient/uvicorn shutdown path) — not only on a graceful WebSocketDisconnect.
        try:
            await self._stop.wait()
        finally:
            await self._teardown(inbound, writer)

    async def _inbound(self) -> None:
        try:
            while True:
                event = _parse_inbound(await self._ws.receive_text())
                if event is None:
                    # INVARIANT: enqueue the nack — the inbound task never calls ws.send.
                    self._out.put_nowait(
                        _error(
                            self._topic,
                            self._clock,
                            "invalid_frame",
                            "unparseable or invalid inbound frame",
                            None,
                        )
                    )
                    continue
                self._handle(event)
        except WebSocketDisconnect:
            pass
        finally:
            self._stop.set()

    def _handle(self, event: _InboundEvent) -> None:
        if isinstance(event, AttachEvent):
            self._resubscribe(event.data.from_sequence)
        elif isinstance(event, StopEvent):
            if self._job_runner is not None:
                self._job_runner.stop(self._topic)
            else:
                # WHY: no runner ⇒ the Stop cannot act; nack it so the client isn't left guessing.
                self._out.put_nowait(
                    _error(
                        self._topic,
                        self._clock,
                        "unsupported",
                        "stop not supported: no job runner configured",
                        event.id,
                    )
                )

    def _resubscribe(self, cursor: int | None) -> None:
        if self._sub is not None:
            self._sub.cancel()
        sub = asyncio.ensure_future(self._pump(cursor))
        # INVARIANT: the pump's failure must always reach the client. Without this callback the
        # task's exception is swallowed (nothing awaits it) while the writer keeps emitting
        # heartbeats — so a permanently dead stream is indistinguishable from an idle healthy
        # one. That silence is the OME-623 bug; it had already been observed once for a
        # different trigger (see NatsBus.subscribe) and worked around only for that trigger.
        sub.add_done_callback(self._on_pump_done)
        self._sub = sub

    def _on_pump_done(self, task: asyncio.Task[None]) -> None:
        """Report a pump that died of anything other than cancellation.

        WHY cancellation is exempt: :meth:`_resubscribe` cancels the previous pump on every
        re-attach and :meth:`_teardown` cancels it on disconnect — both are normal control flow,
        and nacking them would spam a correctly-behaving client.
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is None:
            return
        # WHY the type name and not str(exc): a broker error can carry connection strings or
        # credentials, and this frame goes to the client. The class is enough to act on; the
        # detail belongs in the server's own logs.
        self._out.put_nowait(
            _error(
                self._topic,
                self._clock,
                "stream_failed",
                f"the topic subscription failed ({type(exc).__name__}); re-attach to resume",
                None,
            )
        )

    async def _pump(self, cursor: int | None) -> None:
        async for event in self._bus.subscribe(self._topic, cursor):
            await self._out.put(event)

    async def _writer(self) -> None:
        try:
            while not self._stop.is_set():
                if not await self._try_send(await self._next()):
                    break
        finally:
            self._stop.set()

    async def _next(self) -> OutboundFrame:
        try:
            return await asyncio.wait_for(self._out.get(), timeout=self._heartbeat_s)
        except TimeoutError:
            return _heartbeat(self._topic, self._clock)

    async def _try_send(self, event: OutboundFrame) -> bool:
        try:
            await _send(self._ws, event)
        except (WebSocketDisconnect, RuntimeError):
            return False
        return True

    async def _teardown(self, *tasks: asyncio.Task[None]) -> None:
        pending = [task for task in (self._sub, *tasks) if task is not None]
        for task in pending:
            task.cancel()
        # WHY: swallow a re-delivered cancellation of *this* await so the drain always completes;
        # the original cancellation (if any) still re-raises out of the enclosing finally.
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*pending, return_exceptions=True)


async def run_bridge(
    ws: WebSocket,
    bus: Bus,
    topic: str,
    *,
    job_runner: JobRunner | None,
    clock: Clock,
    heartbeat_s: float,
) -> None:
    """Run the bridge until the client disconnects (spec §6)."""
    await Bridge(ws, bus, topic, job_runner=job_runner, clock=clock, heartbeat_s=heartbeat_s).run()
