"""A failed drain must not strand the stream it was draining (OME-315).

FEATURE: cancelling an in-flight run over REST.
STORY: as an operator, a broker hiccup while cancelling must not leave a stream behind forever.

`stop_run` drains the run's terminal frame before reclaiming the stream, and states the rule it
works to: "best-effort and BOUNDED … so teardown below is unconditional." It was not. The drain
absorbs only `TimeoutError`, while the read underneath it can fail other ways — `subscribe` on a
broker-backed adapter (consumer creation, a stream deleted between `exists` and the read, a NATS
blip), or `_scan_terminal`'s own `RuntimeError` when a stream ends with no terminal frame. Any of
those propagated out of the route BEFORE `delete_stream`, so the Job was gone and the stream, its
consumer state and its filestore directory survived — the exact permanent-per-run leak the
`delete`-and-not-`purge` comment two lines below exists to prevent.

INVARIANT: the drain is an OPTIMISATION over teardown, never a precondition for it. A drain that
fails costs a terminal frame; a teardown that is skipped costs a stream forever, and the caller
cannot tell it happened.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from _fakes import FixedGate, RecordingJobRunner
from fastapi import FastAPI
from httpx import ASGITransport

from url4.streaming.protocol import OutboundFrame, StartedData, StartedEvent
from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.testing import InMemoryEventStream

SECRET = "stop-drain-error-secret"
WINDOW_S = 60
T0 = datetime(2026, 8, 3, 9, 0, 0, tzinfo=UTC)
TOPIC = "topic-drain-error"


def _cap(topic: str) -> dict[str, str]:
    return {"URL4-Capability": JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)}


class _ReclaimRecordingStream(InMemoryEventStream):
    """Records whether the reclaim ran — the whole assertion of this module."""

    def __init__(self) -> None:
        super().__init__()
        self.reclaimed = False

    async def purge(self, topic: str) -> None:
        self.reclaimed = True
        await super().purge(topic)


class _RaisingSubscribeStream(_ReclaimRecordingStream):
    """`subscribe` fails outright — the broker-adapter failure mode."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self._error = error

    def subscribe(self, topic: str, from_sequence: int | None = None):  # type: ignore[no-untyped-def]
        raise self._error


class _TerminalLessStream(_ReclaimRecordingStream):
    """A stream that ends without a terminal frame — `_scan_terminal`'s own `RuntimeError`."""

    def subscribe(  # type: ignore[override]
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]:
        async def _empty() -> AsyncIterator[OutboundFrame]:
            return
            yield  # pragma: no cover - makes this an async generator

        return _empty()


def _make_app(*, stream: InMemoryEventStream, job_runner: RecordingJobRunner) -> FastAPI:
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S, stop_drain_s=5.0)
    return create_app(
        settings,
        stream=stream,
        job_runner=job_runner,
        clock=lambda: T0,
        interest=FixedGate(True),
    )


def _started(topic: str) -> OutboundFrame:
    return StartedEvent(
        id=f"start-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=StartedData(url4="gpt()"),
    )


async def _delete(app: FastAPI) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.delete("/", params={"topic": TOPIC}, headers=_cap(TOPIC))


# --- the leak -------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ConnectionError("broker unreachable"),
        RuntimeError("consumer could not be created"),
    ],
    ids=["connection", "runtime"],
)
async def test_a_failing_drain_still_reclaims_the_stream(error: Exception) -> None:
    stream = _RaisingSubscribeStream(error)
    await stream.publish(TOPIC, _started(TOPIC))
    runner = RecordingJobRunner(exists=True)

    resp = await _delete(_make_app(stream=stream, job_runner=runner))

    assert resp.status_code == 204
    assert stream.reclaimed


@pytest.mark.asyncio
async def test_a_stream_that_ends_without_a_terminal_frame_still_reclaims() -> None:
    """`_scan_terminal` raises on this itself, so the guard has to cover more than the broker."""
    stream = _TerminalLessStream()
    await stream.publish(TOPIC, _started(TOPIC))
    runner = RecordingJobRunner(exists=True)

    resp = await _delete(_make_app(stream=stream, job_runner=runner))

    assert resp.status_code == 204
    assert stream.reclaimed


@pytest.mark.asyncio
async def test_a_failing_drain_is_not_reported_as_a_server_error() -> None:
    """INVARIANT: DELETE stays idempotent and quiet. The drain is best-effort, so its failure is
    not the caller's problem — the Job is stopped and the stream is reclaimed either way, and a
    500 would invite a retry that has nothing left to do."""
    stream = _RaisingSubscribeStream(ConnectionError("broker unreachable"))
    await stream.publish(TOPIC, _started(TOPIC))
    runner = RecordingJobRunner(exists=True)

    resp = await _delete(_make_app(stream=stream, job_runner=runner))

    assert resp.status_code == 204
    assert runner.stopped == [TOPIC]
