"""`from_sequence` is 1-based, and every layer must agree on that (OME-623).

INVARIANT: CloudEvents stream sequences start at 1; `None` means "from the start". A value below
1 is a malformed frame, not a legal "everything" shorthand.

STORY: as a client I attach with `{"from_sequence": 0}`. That validated cleanly, reached
JetStream as `opt_start_seq=0`, was rejected there, and killed the bridge's subscription task —
which ran with no done-callback, so the exception vanished and I received heartbeats forever while
the run completed and every frame sat unread in the stream. Observed on a live kind cluster.

WHY these two layers are tested together: the bug survived because they DISAGREED.
`InMemoryBus` filtered `seq >= from_sequence`, so 0 matched everything and replayed the whole
stream, while JetStream rejects the consumer outright. The double was more permissive than
production, so no headless test could reproduce a real hang. Pinning the bound in the protocol
model AND asserting it as a Bus-contract conformance across both adapters is what closes that gap.
"""

import asyncio
import uuid
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from url4_cloud_nats import Bus, InMemoryBus, NatsBus
from url4_streaming_protocol import AttachData, OutboundFrame

# INVARIANT: factories, not instances — mirrors tests/unit/test_nats_bus.py so a conformance
# assertion binds BOTH adapters; NatsBus stays owner-run (real broker, INFRA rule).
BUS_FACTORIES: list[object] = [
    pytest.param(InMemoryBus, id="InMemoryBus"),
    pytest.param(
        lambda: NatsBus("nats://localhost:4222"),
        id="NatsBus",
        marks=pytest.mark.skip(reason="owner-run: needs real NATS (INFRA rule)"),
    ),
]


def _topic() -> str:
    return f"bounds-{uuid.uuid4().hex[:8]}"


async def _drain_one(bus: Bus, topic: str, from_sequence: int | None) -> list[OutboundFrame]:
    out: list[OutboundFrame] = []
    async for ev in bus.subscribe(topic, from_sequence):
        out.append(ev)
        break
    return out


# --- the protocol edge ---------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1])
def test_attach_data_rejects_from_sequence_below_one(bad: int) -> None:
    """A malformed attach must fail validation, so the bridge's existing `invalid_frame` nack
    path answers it — instead of the value travelling on to the bus."""
    with pytest.raises(ValidationError):
        AttachData(from_sequence=bad)


@pytest.mark.parametrize("ok", [None, 1, 2])
def test_attach_data_accepts_none_and_one_based_values(ok: int | None) -> None:
    """Guard the boundary from the other side: 1 is the first legal sequence and None means
    "from the start" — the new lower bound must catch neither."""
    assert AttachData(from_sequence=ok).from_sequence == ok


# --- the Bus contract, asserted across every adapter ----------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("make_bus", BUS_FACTORIES)
@pytest.mark.parametrize("bad", [0, -1])
async def test_conformance_subscribe_rejects_out_of_range_from_sequence(
    make_bus: Callable[[], Bus], bad: int
) -> None:
    """Bus contract: an out-of-range cursor is a caller error EVERY adapter rejects identically.

    Before this, `InMemoryBus` silently replayed from the beginning while JetStream refused the
    consumer — the exact divergence that let the production hang through the headless suite.
    """
    bus = make_bus()
    with pytest.raises(ValueError):
        await _drain_one(bus, _topic(), bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("make_bus", BUS_FACTORIES)
@pytest.mark.parametrize("cursor", [None, 1])
async def test_conformance_subscribe_still_accepts_one_and_none(
    make_bus: Callable[[], Bus], cursor: int | None
) -> None:
    """The guard must not have narrowed the legal range: `1` and `None` still subscribe.

    WHY a timeout is the assertion: `subscribe` is an async generator, so the guard does not run
    until the first `__anext__`. Waiting on an empty topic therefore proves BOTH that the value
    was accepted (no `ValueError`) and that the subscription is live and waiting for frames —
    a `TimeoutError` here is the pass condition, not a flake.
    """
    bus = make_bus()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.25):
            await _drain_one(bus, _topic(), cursor)
