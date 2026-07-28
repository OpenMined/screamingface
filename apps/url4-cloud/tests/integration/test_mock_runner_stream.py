"""OME-524 — §8 invariants on the raw mock-runner stream (spec §11; docs/protocol.md §8).

Headless: the multi-node :func:`publish_mock_run` publishes to an :class:`InMemoryBus`; the drained
frames are re-validated through :data:`OutboundFrameAdapter` and asserted §8-valid — monotonic
sequence, cost roll-up (``subtree.total == Σ self``), a well-formed span tree, and ordering
(``CostUsage{subtree}`` before ``Result``). No live NATS/Docker (INFRA rule).
"""

import asyncio
from decimal import Decimal

import pytest

from url4_cloud.testing.mock_runner import build_run, publish_mock_run
from url4_cloud_nats import InMemoryBus
from url4_streaming_protocol import (
    CostUsageEvent,
    OutboundFrame,
    OutboundFrameAdapter,
    ResultEvent,
    SpanEvent,
    StartedEvent,
    TerminatedEvent,
)

TOPIC = "e2e-mock-topic"
EXPR = "(gpt,claude)!'hi'"

_EXPECTED_TYPES = [
    "ai.url4.started",
    "ai.url4.log",
    "ai.url4.span",
    "ai.url4.span",
    "ai.url4.cost.usage",
    "ai.url4.span",
    "ai.url4.cost.usage",
    "ai.url4.cost.usage",
    "ai.url4.cost.usage",
    "ai.url4.result",
    "ai.url4.terminated",
]


async def _drain(bus: InMemoryBus, topic: str, n: int) -> list[OutboundFrame]:
    out: list[OutboundFrame] = []

    async def _run() -> None:
        async for event in bus.subscribe(topic, from_sequence=1):
            out.append(event)
            if len(out) >= n:
                break

    await asyncio.wait_for(_run(), timeout=2.0)
    return out


def _span_id(event: SpanEvent) -> str:
    # W3C traceparent: 00-<32hex trace>-<16hex span>-<2hex flags>.
    assert event.traceparent is not None
    return event.traceparent.split("-")[2]


def _parent_span_id(event: SpanEvent) -> str | None:
    # The mock carries parent linkage in the CloudEvents tracestate: `url4.parent=<hex>`.
    if event.tracestate is None:
        return None
    return event.tracestate.split("=", 1)[1]


@pytest.mark.asyncio
async def test_mock_stream_is_a_valid_ordered_cloudevents_lifecycle() -> None:
    bus = InMemoryBus()
    await publish_mock_run(bus, TOPIC, EXPR)
    frames = await _drain(bus, TOPIC, len(_EXPECTED_TYPES))

    assert [f.type for f in frames] == _EXPECTED_TYPES
    # Every streamed frame round-trips through the wire adapter (spec §11 / §12).
    for frame in frames:
        wire = frame.model_dump(mode="json", by_alias=True)
        assert OutboundFrameAdapter.validate_python(wire).type == frame.type
    # Monotonic, gapless sequence assigned by the stream (docs/protocol.md §6).
    assert [int(f.sequence) for f in frames if f.sequence is not None] == list(range(1, 12))
    assert isinstance(frames[0], StartedEvent)
    last = frames[-1]
    assert isinstance(last, TerminatedEvent)
    assert last.data.status == "succeeded"


@pytest.mark.asyncio
async def test_mock_stream_cost_rolls_up_and_precedes_result() -> None:
    bus = InMemoryBus()
    await publish_mock_run(bus, TOPIC, EXPR)
    frames = await _drain(bus, TOPIC, len(_EXPECTED_TYPES))

    costs = [f for f in frames if isinstance(f, CostUsageEvent)]
    selfs = [c for c in costs if c.data.scope == "self"]
    subtrees = [c for c in costs if c.data.scope == "subtree"]
    assert len(selfs) == 3 and len(subtrees) == 1
    subtree = subtrees[0]

    # §8: subtree.total == self + Σ children.self (the whole point of a MULTI-node mock).
    assert subtree.data.cost.total_usd == sum((c.data.cost.total_usd for c in selfs), Decimal("0"))
    # Token usage rolls up the same way.
    assert subtree.data.usage.input_tokens == sum(c.data.usage.input_tokens for c in selfs)
    assert subtree.data.usage.output_tokens == sum(c.data.usage.output_tokens for c in selfs)

    # §8 ordering: CostUsage{subtree} is emitted before Result.
    types = [f.type for f in frames]
    subtree_idx = frames.index(subtree)
    result_idx = next(i for i, f in enumerate(frames) if isinstance(f, ResultEvent))
    assert subtree_idx < result_idx
    assert types.index("ai.url4.terminated") == len(frames) - 1


@pytest.mark.asyncio
async def test_mock_stream_has_a_well_formed_span_tree() -> None:
    bus = InMemoryBus()
    await publish_mock_run(bus, TOPIC, EXPR)
    frames = await _drain(bus, TOPIC, len(_EXPECTED_TYPES))

    spans = [f for f in frames if isinstance(f, SpanEvent)]
    assert len(spans) == 3
    seen: set[str] = set()
    roots = 0
    for span in spans:
        parent = _parent_span_id(span)
        if parent is None:
            roots += 1
        else:
            # §8: every parent_span_id refers to an already-emitted parent span.
            assert parent in seen
        seen.add(_span_id(span))
    assert roots == 1  # exactly one root; the rest hang off it
    assert len(seen) == 3  # span ids are unique


def test_build_run_is_pure_and_deterministic_in_shape() -> None:
    # build_run is the pure §8 sequence the publisher emits; two calls agree on structure.
    a = build_run(TOPIC, EXPR)
    b = build_run(TOPIC, EXPR)
    assert [e.type for e in a] == _EXPECTED_TYPES
    assert [e.type for e in b] == _EXPECTED_TYPES
    assert all(e.subject == TOPIC for e in a)
