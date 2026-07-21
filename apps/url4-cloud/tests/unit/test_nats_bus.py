import asyncio
from datetime import datetime

import pytest

from url4_cloud_nats import Bus, InMemoryBus, NatsBus
from url4_streaming_protocol import LogData, LogEvent, OutboundFrame, SpanData, SpanEvent

TOPIC = "cap-topic"


def _log_event(n: int) -> LogEvent:
    return LogEvent(
        id=f"e{n}",
        source="/trace/t/node/root",
        subject="t",
        data=LogData(severity_number=9, severity_text="INFO", body=f"msg-{n}"),
    )


async def _take(
    bus: Bus, topic: str, n: int, from_sequence: int | None = None
) -> list[OutboundFrame]:
    out: list[OutboundFrame] = []

    async def _run() -> None:
        async for ev in bus.subscribe(topic, from_sequence):
            out.append(ev)
            if len(out) >= n:
                break

    await asyncio.wait_for(_run(), timeout=2.0)
    return out


@pytest.mark.asyncio
async def test_publish_subscribe_round_trips_in_order() -> None:
    bus = InMemoryBus()
    for i in range(3):
        await bus.publish(TOPIC, _log_event(i))
    got = await _take(bus, TOPIC, 3)
    bodies = []
    for ev in got:
        assert isinstance(ev, LogEvent)
        bodies.append(ev.data.body)
    assert bodies == ["msg-0", "msg-1", "msg-2"]
    assert [ev.id for ev in got] == ["e0", "e1", "e2"]


@pytest.mark.asyncio
async def test_gen_ai_aliases_survive_the_codec() -> None:
    bus = InMemoryBus()
    span = SpanEvent(
        id="s1",
        source="/trace/t/node/n",
        data=SpanData(
            name="chat",
            operation="chat",
            input_tokens=1200,
            output_tokens=340,
            start=datetime(2026, 7, 21, 9, 0, 0),
        ),
    )
    await bus.publish(TOPIC, span)
    got = await _take(bus, TOPIC, 1)
    ev = got[0]
    assert isinstance(ev, SpanEvent)
    assert ev.data.input_tokens == 1200
    assert ev.data.output_tokens == 340
    assert ev.data.operation == "chat"


@pytest.mark.asyncio
async def test_sequence_is_monotonic_from_one() -> None:
    bus = InMemoryBus()
    for i in range(3):
        await bus.publish(TOPIC, _log_event(i))
    got = await _take(bus, TOPIC, 3)
    assert [ev.sequence for ev in got] == ["1", "2", "3"]
    assert all(ev.sequencetype == "Integer" for ev in got)


@pytest.mark.asyncio
async def test_from_sequence_replays_the_gap_inclusive() -> None:
    bus = InMemoryBus()
    for i in range(3):
        await bus.publish(TOPIC, _log_event(i))
    got = await _take(bus, TOPIC, 2, from_sequence=2)
    assert [ev.sequence for ev in got] == ["2", "3"]
    bodies = []
    for ev in got:
        assert isinstance(ev, LogEvent)
        bodies.append(ev.data.body)
    assert bodies == ["msg-1", "msg-2"]


@pytest.mark.asyncio
async def test_live_delivery_when_subscribed_before_publish() -> None:
    bus = InMemoryBus()
    await bus.ensure_stream(TOPIC)
    task = asyncio.create_task(_take(bus, TOPIC, 1))
    await asyncio.sleep(0.05)  # let the subscriber reach its wait
    await bus.publish(TOPIC, _log_event(7))
    got = await asyncio.wait_for(task, timeout=2.0)
    ev = got[0]
    assert isinstance(ev, LogEvent)
    assert ev.data.body == "msg-7"


@pytest.mark.asyncio
async def test_purge_clears_frames_but_keeps_sequence_counting() -> None:
    bus = InMemoryBus()
    await bus.publish(TOPIC, _log_event(0))
    await bus.publish(TOPIC, _log_event(1))
    await bus.purge(TOPIC)
    await bus.publish(TOPIC, _log_event(99))
    got = await _take(bus, TOPIC, 1, from_sequence=1)
    ev = got[0]
    assert isinstance(ev, LogEvent)
    # The two purged frames (seq 1,2) are gone; the survivor keeps the monotonic seq 3.
    assert ev.sequence == "3"
    assert ev.data.body == "msg-99"


def test_both_implementations_satisfy_the_bus_port() -> None:
    memory: Bus = InMemoryBus()
    remote: Bus = NatsBus("nats://localhost:4222")
    assert isinstance(memory, InMemoryBus)
    assert isinstance(remote, NatsBus)
