"""`DELETE /` gives the run's terminal frame a chance to land before reclaiming the stream.

FEATURE: cancelling an in-flight run (OME-315).
STORY: as a client that cancelled over REST, I need the run's `terminated: stopped` frame to
survive the teardown that cancel triggered.

The route stops the Job and then reclaims its stream. Those are two different processes: the
Runner pod publishes its terminal frame while it is shutting down, so an immediate reclaim
races it — and wins. Dropping the frame here would undo, on the REST path, exactly what the
Runner's signal handling exists to produce.
"""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from _fakes import FixedGate, RecordingJobRunner
from fastapi import FastAPI
from httpx import ASGITransport

from url4.streaming.protocol import (
    OutboundFrame,
    StartedData,
    StartedEvent,
    TerminatedData,
    TerminatedEvent,
)
from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.testing import InMemoryEventStream

SECRET = "stop-drain-secret"
WINDOW_S = 60
T0 = datetime(2026, 8, 3, 9, 0, 0, tzinfo=UTC)
TOPIC = "topic-drain"


def _cap(topic: str) -> dict[str, str]:
    return {"URL4-Capability": JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)}


class _DrainAwareStream(InMemoryEventStream):
    """Records how much history survived to the reclaim, and when a reader attached.

    `subscribed` fires when the route opens its drain subscription — the runner below publishes
    off that, so the test needs no sleep and no wall clock to order the two.
    """

    def __init__(self) -> None:
        super().__init__()
        self.subscribed = asyncio.Event()
        self.frames_at_purge: int | None = None

    def subscribe(self, topic: str, from_sequence: int | None = None):  # type: ignore[no-untyped-def]
        self.subscribed.set()
        return super().subscribe(topic, from_sequence)

    async def purge(self, topic: str) -> None:
        # The retained history AT the moment of reclaim is the whole assertion — read after the
        # fact it is always empty, whether or not the drain waited.
        self.frames_at_purge = len(self._log.get(topic, []))  # noqa: SLF001
        await super().purge(topic)


class _TerminatingJobRunner(RecordingJobRunner):
    """A live run whose pod publishes `terminated: stopped` only once someone is listening.

    Models the real ordering — the frame arrives AFTER `stop()` returns, from a different
    process — without a timer. If the route never drains, nothing is ever published, which is
    precisely the behaviour under test.
    """

    def __init__(self, stream: _DrainAwareStream) -> None:
        super().__init__(exists=True)
        self._stream = stream
        self.publisher: asyncio.Task[None] | None = None

    async def stop(self, topic: str) -> None:
        await super().stop(topic)
        self.publisher = asyncio.create_task(self._publish_terminal(topic))

    async def _publish_terminal(self, topic: str) -> None:
        await self._stream.subscribed.wait()
        await self._stream.publish(topic, _terminated(topic))


def _make_app(
    *,
    stream: InMemoryEventStream,
    job_runner: RecordingJobRunner,
    stop_drain_s: float = 5.0,
) -> FastAPI:
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S, stop_drain_s=stop_drain_s)
    return create_app(
        settings,
        stream=stream,
        job_runner=job_runner,
        clock=lambda: T0,
        interest=FixedGate(True),
    )


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _started(topic: str) -> OutboundFrame:
    return StartedEvent(
        id=f"start-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=StartedData(url4="gpt()"),
    )


def _terminated(topic: str) -> OutboundFrame:
    return TerminatedEvent(
        id=f"term-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=TerminatedData(status="stopped"),
    )


async def _delete(app: FastAPI) -> httpx.Response:
    async with _client(app) as client:
        return await client.delete("/", params={"topic": TOPIC}, headers=_cap(TOPIC))


@pytest.mark.asyncio
async def test_the_terminal_frame_lands_before_the_stream_is_reclaimed() -> None:
    """The headline: cancel must not delete the evidence that the cancel took effect."""
    stream = _DrainAwareStream()
    await stream.publish(TOPIC, _started(TOPIC))
    runner = _TerminatingJobRunner(stream)

    resp = await _delete(_make_app(stream=stream, job_runner=runner))

    assert resp.status_code == 204
    assert runner.stopped == [TOPIC]
    # Started + Terminated: the reclaim happened downstream of the frame, not in a race with it.
    assert stream.frames_at_purge == 2


@pytest.mark.asyncio
async def test_an_absent_run_is_torn_down_without_waiting() -> None:
    """INVARIANT: DELETE stays fast and idempotent when there is nothing to stop.

    Draining unconditionally would make every repeat DELETE — the documented idempotent case —
    pay the full bound waiting for a frame no process will ever publish.
    """
    stream = _DrainAwareStream()
    await stream.publish(TOPIC, _started(TOPIC))
    runner = RecordingJobRunner(exists=False)

    resp = await _delete(_make_app(stream=stream, job_runner=runner, stop_drain_s=30.0))

    assert resp.status_code == 204
    assert not stream.subscribed.is_set()
    assert stream.frames_at_purge == 1


@pytest.mark.asyncio
async def test_teardown_happens_even_when_the_frame_never_arrives() -> None:
    """INVARIANT: the drain is best-effort. A pod that dies without publishing — SIGKILL after
    the grace period, a lost broker — must not strand the stream it was holding."""
    stream = _DrainAwareStream()
    await stream.publish(TOPIC, _started(TOPIC))
    runner = RecordingJobRunner(exists=True)  # never publishes anything

    resp = await _delete(_make_app(stream=stream, job_runner=runner, stop_drain_s=0.05))

    assert resp.status_code == 204
    assert stream.subscribed.is_set()
    assert stream._log[TOPIC] == []  # noqa: SLF001 — asserting the reclaim side effect
