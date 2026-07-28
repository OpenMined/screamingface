from __future__ import annotations

import asyncio
from collections.abc import Callable

from url4.streaming.interfaces import EventStream
from url4.streaming.protocol import LogData, LogEvent, OutboundFrame
from url4.streaming.testing.collect import TAKE_TIMEOUT_S, take

EventStreamFactory = Callable[[], EventStream]

_TOPIC = "stream-contract-topic"


def _frame(n: int) -> LogEvent:
    return LogEvent(
        id=f"contract-{n}",
        source="/trace/contract/node/root",
        subject=_TOPIC,
        data=LogData.at("INFO", f"body-{n}"),
    )


def _body(frame: OutboundFrame) -> str:
    assert isinstance(frame, LogEvent), f"expected a LogEvent back, got {type(frame).__name__}"
    return frame.data.body


async def _take(
    stream: EventStream, n: int, from_sequence: int | None = None
) -> list[OutboundFrame]:
    try:
        return await take(stream, _TOPIC, n, from_sequence)
    except TimeoutError as exc:  # pragma: no cover - only on a non-conforming adapter
        raise AssertionError(
            f"subscribe(from_sequence={from_sequence!r}) did not deliver {n} frames "
            f"within {TAKE_TIMEOUT_S}s — a stalled subscription looks identical to an idle "
            f"healthy one"
        ) from exc


async def _sequence_is_one_based_and_monotonic(stream: EventStream) -> None:
    for i in range(3):
        await stream.publish(_TOPIC, _frame(i))
    got = await _take(stream, 3)
    sequences = [f.sequence for f in got]
    assert sequences == ["1", "2", "3"], (
        f"stream sequences must be 1-based and monotonic (docs/protocol.md §6), got {sequences}"
    )
    assert [_body(f) for f in got] == ["body-0", "body-1", "body-2"], "frames must arrive in order"


async def _replay_from_sequence_is_inclusive_then_live(stream: EventStream) -> None:
    for i in range(3):
        await stream.publish(_TOPIC, _frame(i))
    replayed = await _take(stream, 2, from_sequence=2)
    assert [_body(f) for f in replayed] == ["body-1", "body-2"], (
        f"from_sequence must be inclusive, got {[_body(f) for f in replayed]}"
    )

    live: list[OutboundFrame] = []

    async def _follow() -> None:
        async for event in stream.subscribe(_TOPIC, 4):
            live.append(event)
            return

    follower = asyncio.ensure_future(_follow())
    await asyncio.sleep(0)
    await stream.publish(_TOPIC, _frame(99))
    try:
        await asyncio.wait_for(follower, timeout=TAKE_TIMEOUT_S)
    except TimeoutError as exc:  # pragma: no cover - only on a non-conforming adapter
        follower.cancel()
        raise AssertionError(
            "a replay subscription must continue LIVE past the replayed gap — this one never "
            "delivered a frame published after it attached"
        ) from exc
    assert [_body(f) for f in live] == ["body-99"], f"expected the live frame, got {live}"


async def _from_sequence_below_one_is_rejected(stream: EventStream) -> None:
    for bad in (0, -1):
        try:
            agen = stream.subscribe(_TOPIC, bad)
            await agen.__anext__()
        except ValueError:
            continue
        except Exception as exc:  # noqa: BLE001 - any other failure is still a contract breach
            raise AssertionError(
                f"subscribe(from_sequence={bad}) must raise ValueError, raised "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        raise AssertionError(
            f"subscribe(from_sequence={bad}) must raise ValueError — 'None' means from the start, "
            f"and accepting {bad} silently replays the whole stream"
        )


async def _purge_drops_frames_but_keeps_counting(stream: EventStream) -> None:
    for i in range(2):
        await stream.publish(_TOPIC, _frame(i))
    await stream.purge(_TOPIC)
    await stream.publish(_TOPIC, _frame(7))
    got = await _take(stream, 1)
    assert _body(got[0]) == "body-7", f"purge must drop buffered frames, got {_body(got[0])!r}"
    assert got[0].sequence == "3", (
        f"purge must NOT rewind the stream counter (a reused sequence would break replay), "
        f"got {got[0].sequence}"
    )


async def _subscribe_before_first_publish_works(stream: EventStream) -> None:
    frames: list[OutboundFrame] = []

    async def _follow() -> None:
        async for event in stream.subscribe(_TOPIC):
            frames.append(event)
            return

    follower = asyncio.ensure_future(_follow())
    await asyncio.sleep(0)
    await stream.publish(_TOPIC, _frame(5))
    try:
        await asyncio.wait_for(follower, timeout=TAKE_TIMEOUT_S)
    except TimeoutError as exc:  # pragma: no cover - only on a non-conforming adapter
        follower.cancel()
        raise AssertionError(
            "subscribing before the first publish must work — the 428 interest gate makes it the "
            "normal ordering, so the stream has to be ensured rather than merely bound"
        ) from exc
    assert [_body(f) for f in frames] == ["body-5"]


async def _ensure_stream_is_idempotent(stream: EventStream) -> None:
    await stream.ensure_stream(_TOPIC)
    await stream.ensure_stream(_TOPIC)
    await stream.publish(_TOPIC, _frame(1))
    got = await _take(stream, 1)
    assert got[0].sequence == "1"


_CHECKS = (
    _ensure_stream_is_idempotent,
    _sequence_is_one_based_and_monotonic,
    _replay_from_sequence_is_inclusive_then_live,
    _from_sequence_below_one_is_rejected,
    _purge_drops_frames_but_keeps_counting,
    _subscribe_before_first_publish_works,
)


async def assert_stream_conformance(make_bus: EventStreamFactory) -> None:
    for check in _CHECKS:
        try:
            await check(make_bus())
        except AssertionError as exc:
            raise AssertionError(
                f"EventStream contract '{check.__name__.strip('_')}': {exc}"
            ) from exc


__all__ = ["EventStreamFactory", "assert_stream_conformance"]
