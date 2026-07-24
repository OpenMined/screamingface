import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime

import pytest

from url4_cloud_nats import Bus, InMemoryBus, NatsBus
from url4_streaming_protocol import LogData, LogEvent, OutboundFrame, SpanData, SpanEvent

TOPIC = "cap-topic"

# INVARIANT: factories, not instances — each conformance test builds its own bus so InMemoryBus
# tests stay isolated from one another; NatsBus is owner-run only (real broker, INFRA rule).
BUS_FACTORIES: list[object] = [
    pytest.param(InMemoryBus, id="InMemoryBus"),
    pytest.param(
        lambda: NatsBus("nats://localhost:4222"),
        id="NatsBus",
        marks=pytest.mark.skip(reason="owner-run: needs real NATS (INFRA rule)"),
    ),
]


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


def test_both_implementations_satisfy_the_bus_port() -> None:
    memory: Bus = InMemoryBus()
    remote: Bus = NatsBus("nats://localhost:4222")
    assert isinstance(memory, InMemoryBus)
    assert isinstance(remote, NatsBus)


def _topic() -> str:
    # WHY: a fresh topic per conformance test call — cheap for InMemoryBus, and avoids stream
    # collisions across repeated owner-runs against a real, persistent NATS broker.
    return f"cap-topic-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
@pytest.mark.parametrize("make_bus", BUS_FACTORIES)
async def test_conformance_sequence_is_monotonic_from_one(
    make_bus: Callable[[], Bus],
) -> None:
    """Bus contract: publish assigns a monotonic, string sequence starting at ``"1"``."""
    bus = make_bus()
    topic = _topic()
    for i in range(3):
        await bus.publish(topic, _log_event(i))
    got = await _take(bus, topic, 3)
    assert [ev.sequence for ev in got] == ["1", "2", "3"]
    assert all(ev.sequencetype == "Integer" for ev in got)


@pytest.mark.asyncio
@pytest.mark.parametrize("make_bus", BUS_FACTORIES)
async def test_conformance_from_sequence_replays_the_gap_then_live(
    make_bus: Callable[[], Bus],
) -> None:
    """Bus contract: ``subscribe(from_sequence=k)`` replays the gap inclusive, then goes live."""
    bus = make_bus()
    topic = _topic()
    for i in range(3):
        await bus.publish(topic, _log_event(i))
    got = await _take(bus, topic, 2, from_sequence=2)
    assert [ev.sequence for ev in got] == ["2", "3"]
    bodies = []
    for ev in got:
        assert isinstance(ev, LogEvent)
        bodies.append(ev.data.body)
    assert bodies == ["msg-1", "msg-2"]

    live_task = asyncio.create_task(_take(bus, topic, 1, from_sequence=4))
    await asyncio.sleep(0.05)  # let the subscriber reach its wait
    await bus.publish(topic, _log_event(99))
    live = await asyncio.wait_for(live_task, timeout=2.0)
    ev = live[0]
    assert isinstance(ev, LogEvent)
    assert ev.sequence == "4"
    assert ev.data.body == "msg-99"


@pytest.mark.asyncio
@pytest.mark.parametrize("make_bus", BUS_FACTORIES)
async def test_conformance_purge_clears_frames_but_keeps_sequence_counting(
    make_bus: Callable[[], Bus],
) -> None:
    """Bus contract: ``purge`` drops buffered frames while the sequence counter keeps advancing."""
    bus = make_bus()
    topic = _topic()
    await bus.publish(topic, _log_event(0))
    await bus.publish(topic, _log_event(1))
    await bus.purge(topic)
    await bus.publish(topic, _log_event(99))
    got = await _take(bus, topic, 1, from_sequence=1)
    ev = got[0]
    assert isinstance(ev, LogEvent)
    # The two purged frames (seq 1,2) are gone; the survivor keeps the monotonic seq 3.
    assert ev.sequence == "3"
    assert ev.data.body == "msg-99"
