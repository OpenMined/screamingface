from decimal import Decimal

import pytest

from url4.streaming.protocol import (
    CostUsageEvent,
    OutboundFrameAdapter,
    ResultEvent,
    SpanEvent,
    StartedEvent,
    TerminatedEvent,
)
from url4.streaming.testing import take
from url4_cloud.testing import InMemoryEventStream
from url4_cloud.testing.mock_runner import build_run, publish_mock_run

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


def _span_id(event: SpanEvent) -> str:
    assert event.traceparent is not None
    return event.traceparent.split("-")[2]


def _parent_span_id(event: SpanEvent) -> str | None:
    if event.tracestate is None:
        return None
    return event.tracestate.split("=", 1)[1]


@pytest.mark.asyncio
async def test_mock_stream_is_a_valid_ordered_cloudevents_lifecycle() -> None:
    stream = InMemoryEventStream()
    await publish_mock_run(stream, TOPIC, EXPR)
    frames = await take(stream, TOPIC, len(_EXPECTED_TYPES))

    assert [f.type for f in frames] == _EXPECTED_TYPES
    for frame in frames:
        wire = frame.model_dump(mode="json", by_alias=True)
        assert OutboundFrameAdapter.validate_python(wire).type == frame.type
    assert [int(f.sequence) for f in frames if f.sequence is not None] == list(range(1, 12))
    assert isinstance(frames[0], StartedEvent)
    last = frames[-1]
    assert isinstance(last, TerminatedEvent)
    assert last.data.status == "succeeded"


@pytest.mark.asyncio
async def test_mock_stream_cost_rolls_up_and_precedes_result() -> None:
    stream = InMemoryEventStream()
    await publish_mock_run(stream, TOPIC, EXPR)
    frames = await take(stream, TOPIC, len(_EXPECTED_TYPES))

    costs = [f for f in frames if isinstance(f, CostUsageEvent)]
    selfs = [c for c in costs if c.data.scope == "self"]
    subtrees = [c for c in costs if c.data.scope == "subtree"]
    assert len(selfs) == 3 and len(subtrees) == 1
    subtree = subtrees[0]

    assert subtree.data.cost.total_usd == sum((c.data.cost.total_usd for c in selfs), Decimal("0"))
    assert subtree.data.usage.input_tokens == sum(c.data.usage.input_tokens for c in selfs)
    assert subtree.data.usage.output_tokens == sum(c.data.usage.output_tokens for c in selfs)

    types = [f.type for f in frames]
    subtree_idx = frames.index(subtree)
    result_idx = next(i for i, f in enumerate(frames) if isinstance(f, ResultEvent))
    assert subtree_idx < result_idx
    assert types.index("ai.url4.terminated") == len(frames) - 1


@pytest.mark.asyncio
async def test_mock_stream_has_a_well_formed_span_tree() -> None:
    stream = InMemoryEventStream()
    await publish_mock_run(stream, TOPIC, EXPR)
    frames = await take(stream, TOPIC, len(_EXPECTED_TYPES))

    spans = [f for f in frames if isinstance(f, SpanEvent)]
    assert len(spans) == 3
    seen: set[str] = set()
    roots = 0
    for span in spans:
        parent = _parent_span_id(span)
        if parent is None:
            roots += 1
        else:
            assert parent in seen
        seen.add(_span_id(span))
    assert roots == 1
    assert len(seen) == 3


def test_build_run_is_pure_and_deterministic_in_shape() -> None:
    a = build_run(TOPIC, EXPR)
    b = build_run(TOPIC, EXPR)
    assert [e.type for e in a] == _EXPECTED_TYPES
    assert [e.type for e in b] == _EXPECTED_TYPES
    assert all(e.subject == TOPIC for e in a)
