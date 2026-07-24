"""mock_runner — a §8-valid MULTI-node CloudEvents publisher for the compose e2e (spec §11).

The compose e2e cannot run real k8s Jobs, so the App's Docker JobRunner schedules *this* instead of
the real url4 engine: it publishes a logically-correct, multi-node run to NATS honouring
docs/protocol.md §8 — a monotonic sequence, ``CostBreakdown.total_usd == Σ parts`` (model-enforced),
per-node ``CostUsage{self}`` plus one root ``CostUsage{subtree}`` whose total == self + Σ children,
a well-formed span tree (each child span's parent refers to an already-emitted span), and
``CostUsage{subtree}`` before ``Result``.

Unlike a single-node executor (``subtree == self``), this fans out to
two leaf nodes, so the subtree roll-up is a non-trivial sum — the property the e2e asserts. The
:class:`~url4_cloud_nats.Bus` is injected so tests drive it against the ``InMemoryBus`` (no NATS);
:func:`main` is the env→``NatsBus`` glue for the compose container, excluded from coverage (INFRA).
"""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal, TypedDict
from uuid import uuid4

from url4_cloud_nats import Bus
from url4_streaming_protocol import (
    CostBreakdown,
    CostUsageData,
    CostUsageEvent,
    LogData,
    LogEvent,
    OutboundFrame,
    ResultData,
    ResultEvent,
    SpanData,
    SpanEvent,
    StartedData,
    StartedEvent,
    TerminatedData,
    TerminatedEvent,
    TokenUsage,
)

# 16-hex W3C span ids; the tree is root ← {leaf-0, leaf-1} (docs/protocol.md §3).
_ROOT_SPAN = "00000000000000a1"
_C0_SPAN = "00000000000000b2"
_C1_SPAN = "00000000000000c3"


class _Envelope(TypedDict):
    """The CloudEvents attributes stamped per event (docs/protocol.md §1, §6)."""

    id: str
    source: str
    subject: str
    time: datetime
    sequence: str
    sequencetype: Literal["Integer"]


class _Emitter:
    """Stamps a fresh envelope per event: uuid4 id, node source, monotonic string sequence."""

    def __init__(self, topic: str) -> None:
        self._topic = topic
        # W3C trace-id (32 hex) derived from the topic so it is stable per run (docs §3).
        self._trace = sha256(topic.encode("utf-8")).hexdigest()[:32]
        self._n = 0

    def next(self, node: str) -> _Envelope:
        self._n += 1
        return _Envelope(
            id=uuid4().hex,
            source=f"/trace/{self._topic}/node/{node}",
            subject=self._topic,
            time=datetime.now(UTC),
            sequence=str(self._n),
            sequencetype="Integer",
        )

    def span_event(self, node: str, span_id: str, parent: str | None, data: SpanData) -> SpanEvent:
        # WHY: the CloudEvents envelope has no parent-span field; carry the tree edge in the W3C
        # tracestate vendor slot so the span tree stays reconstructable downstream (docs §3).
        tracestate = None if parent is None else f"url4.parent={parent}"
        return SpanEvent(
            **self.next(node),
            data=data,
            traceparent=f"00-{self._trace}-{span_id}-01",
            tracestate=tracestate,
        )


def _log(body: str) -> LogData:
    return LogData(severity_number=9, severity_text="INFO", body=body)


def _span(operation: str, in_tokens: int, out_tokens: int) -> SpanData:
    now = datetime.now(UTC)
    return SpanData(
        name=operation,
        operation=operation,
        provider="anthropic",
        request_model="claude-opus-4-8",
        response_model="claude-opus-4-8",
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        start=now,
        end=now,
    )


def _cost(
    scope: Literal["self", "subtree"], in_usd: str, out_usd: str, in_tok: int, out_tok: int
) -> CostUsageData:
    # INVARIANT: total_usd == input + output (the CostBreakdown validator enforces Σ parts).
    return CostUsageData(
        scope=scope,
        provider="anthropic",
        model="claude-opus-4-8",
        pricing_version="2026-07-01",
        usage=TokenUsage(input_tokens=in_tok, output_tokens=out_tok),
        cost=CostBreakdown(
            input_usd=Decimal(in_usd),
            output_usd=Decimal(out_usd),
            total_usd=Decimal(in_usd) + Decimal(out_usd),
        ),
    )


# Per-node self costs + the root subtree roll-up. INVARIANT (docs/protocol.md §8):
# subtree.total (0.0450) == root.self (0.0300) + leaf0.self (0.0100) + leaf1.self (0.0050); tokens
# roll up identically (1400 in / 350 out). Kept as constants so the arithmetic is auditable here.
_ROOT_SELF = _cost("self", "0.0100", "0.0200", 800, 200)
_C0_SELF = _cost("self", "0.0050", "0.0050", 400, 100)
_C1_SELF = _cost("self", "0.0030", "0.0020", 200, 50)
_SUBTREE = _cost("subtree", "0.0180", "0.0270", 1400, 350)


def build_run(topic: str, url4: str) -> list[OutboundFrame]:
    """The ordered §8 CloudEvents lifecycle for a two-leaf fan-out run (pure, no I/O)."""
    em = _Emitter(topic)
    frames: list[OutboundFrame] = []
    frames.append(StartedEvent(**em.next("root"), data=StartedData(url4=url4)))
    frames.append(LogEvent(**em.next("root"), data=_log(f"executing {url4}")))
    frames.append(em.span_event("root", _ROOT_SPAN, None, _span("plan", 800, 200)))
    frames.append(em.span_event("leaf-0", _C0_SPAN, _ROOT_SPAN, _span("chat", 400, 100)))
    frames.append(CostUsageEvent(**em.next("leaf-0"), data=_C0_SELF))
    frames.append(em.span_event("leaf-1", _C1_SPAN, _ROOT_SPAN, _span("chat", 200, 50)))
    frames.append(CostUsageEvent(**em.next("leaf-1"), data=_C1_SELF))
    frames.append(CostUsageEvent(**em.next("root"), data=_ROOT_SELF))
    # INVARIANT: the subtree roll-up is emitted before the Result (docs/protocol.md §8).
    frames.append(CostUsageEvent(**em.next("root"), data=_SUBTREE))
    frames.append(
        ResultEvent(**em.next("root"), data=ResultData(body="[mock] done", media_type="text/plain"))
    )
    frames.append(TerminatedEvent(**em.next("root"), data=TerminatedData(status="succeeded")))
    return frames


async def publish_mock_run(bus: Bus, topic: str, url4: str) -> None:
    """Publish the §8-valid multi-node lifecycle for ``url4`` to ``bus`` on ``topic``."""
    # WHY: ensure the per-topic stream exists before the first publish (NatsBus needs it).
    await bus.ensure_stream(topic)
    for event in build_run(topic, url4):
        await bus.publish(topic, event)


def main() -> None:  # pragma: no cover - real NATS + event loop (INFRA rule, spec §11)
    import asyncio
    import os

    from url4_cloud_nats import NatsBus

    topic = os.environ["URL4_CLOUD_TOPIC"]
    url4 = os.environ.get("URL4_CLOUD_EXPRESSION", "(gpt,claude)!'demo'")
    nats_url = os.environ.get("URL4_CLOUD_NATS_URL", "nats://localhost:4222")
    asyncio.run(publish_mock_run(NatsBus(nats_url), topic, url4))


if __name__ == "__main__":  # pragma: no cover
    main()
