"""A run's totals carry every token class its spans do.

FEATURE: per-run cost reporting (`OME-849`/`OME-869`). `OME-851` folded all five token classes onto
each SPAN but summed only two at run level, so `cache_read_tokens`, `cache_creation_tokens` and
`reasoning_tokens` reached the wire as `0` on the `scope="subtree"` frame. `packages/screamingface`
surfaces all three, so a Report showed zeroes for tokens that were really used.

STORY: as a researcher comparing a cached ensemble against an uncached one, the run summary is
where I look first. A run that reports `cache_read_tokens: 0` while its own spans report 8,000
tells me caching did nothing, which is the opposite of what happened.

INVARIANT under test: the subtree total equals the sum of the self frames, for EVERY class. A
partial total is the one shape a reader cannot detect from the frame alone.

A separate module rather than an append to `test_run_cost_capture.py`: the repo's append-only gate
compares file status, so growing an existing test file reads as a modified prior test even when
the diff is purely additive.
"""

from __future__ import annotations

from decimal import Decimal

from screamingface_engine.runner.executor import _RunState
from url4.observe import NodeFinished, NodeStarted, RunStarted, Usage
from url4.streaming.interfaces import Traced
from url4.streaming.protocol import CostUsageData

_TRACE = "0" * 32
_ROOT = "a" * 16
_CHILD = "b" * 16


def _usage(span_id: str, **kwargs: object) -> Usage:
    """A `Usage` event with the three optional classes defaulting to unreported."""
    fields: dict[str, object] = {
        "provider": "openrouter",
        "model": "openrouter/anthropic/claude-x",
        "input_tokens": 100,
        "output_tokens": 10,
    }
    fields.update(kwargs)
    return Usage(span_id=span_id, **fields)  # type: ignore[arg-type]


def _drive(*usages: Usage) -> tuple[_RunState, list[CostUsageData]]:
    """Replay a one-span run carrying `usages`, exactly as the runner folds it."""
    state = _RunState()
    frames: list[Traced] = []
    state.map(RunStarted(trace_id=_TRACE, root_span_id=_ROOT, expression_hash="h"))
    state.map(NodeStarted(span_id=_ROOT, parent_span_id=None, node_kind="Model", detail="x"))
    for usage in usages:
        frames.extend(state.map(usage))
    frames.extend(state.map(NodeFinished(span_id=_ROOT, status="ok", engine_seq=1)))
    costs = [f.payload for f in frames if isinstance(f.payload, CostUsageData)]
    return state, costs


# ── the defect ─────────────────────────────────────────────────────────────────────────────────


def test_the_run_total_carries_the_cache_and_reasoning_classes() -> None:
    """INVARIANT: the bug. All three reached the wire as `0` while the span reported them."""
    state, _ = _drive(
        _usage(_ROOT, cache_read_tokens=8000, cache_creation_tokens=4000, reasoning_tokens=610)
    )

    usage = state.build_subtree().usage

    assert usage.cache_read_tokens == 8000
    assert usage.cache_creation_tokens == 4000
    assert usage.reasoning_tokens == 610


def test_the_run_total_still_carries_input_and_output() -> None:
    """Regression guard for the two classes that already worked."""
    state, _ = _drive(_usage(_ROOT, cache_read_tokens=8000))

    usage = state.build_subtree().usage

    assert usage.input_tokens == 100
    assert usage.output_tokens == 10


def test_two_calls_sum_every_class() -> None:
    state, _ = _drive(
        _usage(_ROOT, cache_read_tokens=8000, cache_creation_tokens=1, reasoning_tokens=10),
        _usage(_ROOT, cache_read_tokens=2000, cache_creation_tokens=2, reasoning_tokens=20),
    )

    usage = state.build_subtree().usage

    assert usage.cache_read_tokens == 10000
    assert usage.cache_creation_tokens == 3
    assert usage.reasoning_tokens == 30
    assert usage.input_tokens == 200


def test_the_subtree_total_equals_the_sum_of_the_self_frames() -> None:
    """INVARIANT: the property the whole unit restores. A per-span number that does not add up to
    the run number is the shape a reader cannot detect from either frame alone."""
    state, costs = _drive(
        _usage(_ROOT, cache_read_tokens=8000, cache_creation_tokens=4000, reasoning_tokens=610),
        _usage(_ROOT, cache_read_tokens=2000, cache_creation_tokens=1000, reasoning_tokens=90),
    )
    selfs = [c for c in costs if c.scope == "self"]
    subtree = state.build_subtree().usage

    assert len(selfs) == 1
    assert subtree.cache_read_tokens == selfs[0].usage.cache_read_tokens
    assert subtree.cache_creation_tokens == selfs[0].usage.cache_creation_tokens
    assert subtree.reasoning_tokens == selfs[0].usage.reasoning_tokens


# ── the design decision: run-level tokens do NOT poison ────────────────────────────────────────


def test_a_class_only_some_calls_reported_sums_the_reported_ones() -> None:
    """INVARIANT (OME-869): run-level tokens deliberately do NOT poison, unlike money.

    Money poisons because the wire CAN say "unknown" — `pricing_version: "unpriced"`. `TokenUsage`
    has no such escape hatch, so poisoning would publish `0`: a FALSE claim rather than an absent
    one, and it would destroy the real numbers the reporting calls did supply.

    This is the exact mixed-provider shape: one model reports cache reads and no reasoning, the
    other reports reasoning and no cache reads. Poisoning would zero BOTH real figures.
    """
    state, _ = _drive(
        _usage(_ROOT, cache_read_tokens=8000, reasoning_tokens=None),
        _usage(_ROOT, cache_read_tokens=None, reasoning_tokens=610),
    )

    usage = state.build_subtree().usage

    assert usage.cache_read_tokens == 8000
    assert usage.reasoning_tokens == 610


def test_a_class_no_call_reported_stays_zero() -> None:
    """An absent class is `0` on the wire because `TokenUsage` cannot spell anything else."""
    state, _ = _drive(_usage(_ROOT))

    usage = state.build_subtree().usage

    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0
    assert usage.reasoning_tokens == 0


def test_an_explicit_zero_and_an_unreported_class_agree_at_run_level() -> None:
    """A cache hit reports explicit zeros (`OME-868`); an older gateway reports nothing. Both mean
    "add nothing", so a run mixing them must not distinguish them."""
    state, _ = _drive(
        _usage(_ROOT, cache_read_tokens=0),
        _usage(_ROOT, cache_read_tokens=None),
        _usage(_ROOT, cache_read_tokens=7),
    )

    assert state.build_subtree().usage.cache_read_tokens == 7


def test_money_still_poisons_while_tokens_do_not() -> None:
    """INVARIANT: the asymmetry stated outright, so neither rule can be "made consistent" with the
    other by a later reader. Same run, same events: the token class survives, the price does not.
    """
    state, _ = _drive(
        _usage(_ROOT, cache_read_tokens=8000, cost_usd=Decimal("0.001")),
        _usage(_ROOT, cache_read_tokens=None, cost_usd=None),
    )
    subtree = state.build_subtree()

    assert subtree.usage.cache_read_tokens == 8000
    assert subtree.pricing_version == "unpriced"
    assert subtree.cost.total_usd == Decimal("0")
