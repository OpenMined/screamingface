"""``Url4Executor`` — the real url4-engine-backed adapter (spec §7, OME-446).

Every test drives the real ``url4.dag.run`` against a
:class:`~url4.io.static.StaticIOLayer` world — no mocking of the engine itself. Trace-field
stamping (traceparent/tracestate) lives in ``publish.py``/``_Sequencer`` and is covered by
``test_traceparent.py``; this suite covers the adapter's telemetry/cost/lifecycle behavior.
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest
from url4.core.errors import ParseError, ResolutionError
from url4.io.static import StaticIOLayer
from url4.observe import Log, NodeFinished, NodeStarted, RunStarted

from url4_cloud_nats import InMemoryBus
from url4_cloud_runner.executor import Completed, ExecStep, Traced
from url4_cloud_runner.publish import run as publish_run
from url4_cloud_runner.url4_executor import (
    BridgeOverflowError,
    Url4Executor,
    _Bridge,
    deny_by_default_world,
)
from url4_streaming_protocol import LogData, SpanData, StartedEvent, TerminatedEvent

_SRC_ROOT = Path(__file__).resolve().parents[2] / "runner" / "src"


def _unwrap(frame: object) -> object:
    """A ``Traced`` frame's payload, or the frame itself (``Completed``, never wrapped)."""
    return frame.payload if isinstance(frame, Traced) else frame


async def _drain(executor: Url4Executor, url4: object) -> list[object]:
    # WHY `object`, not `str`: two callers below deliberately pass a hand-built DagNode instead
    # of a url4 string — the exact mechanism `test_observe.py` uses to wire `ctx.report_usage`/
    # `ctx.log` without parsing a surface expression. `Executor.execute`'s Protocol pins `url4:
    # str` (executor.py is read-only for this batch); the cast documents that this call
    # intentionally exercises the engine's broader `str | AstNode | Graph | DagNode` target
    # acceptance through that narrower Protocol type, not a real type error.
    return [frame async for frame in executor.execute(cast("str", url4))]


# --- 1. happy path: >=1 SpanData, then exactly one Completed with the real result ------------


@pytest.mark.asyncio
async def test_static_world_yields_span_then_completed_with_real_result() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    executor = Url4Executor(io)

    frames = await _drain(executor, "https://a!go")

    last = frames[-1]
    assert isinstance(last, Completed)
    assert last.result.body == "go\n\nA"  # the engine's real returned string
    spans = [f for f in frames[:-1] if isinstance(_unwrap(f), SpanData)]
    assert len(spans) >= 1
    assert all(isinstance(f, Traced) and f.span is not None for f in spans)


# --- 2. liveness: a frame arrives while the run is still mid-flight ---------------------------


@pytest.mark.asyncio
async def test_frame_streams_before_the_run_finishes() -> None:
    gate = asyncio.Event()

    async def gated(_context: str, _intent: str) -> str:
        await gate.wait()
        return "GATED"

    io = StaticIOLayer(
        fetch_map={"https://fast": "FAST"},
        routes={"/gated": gated},
    )
    executor = Url4Executor(io)
    gen = executor.execute("(f=https://fast, g=/gated()!go)!'$f $g'")

    first = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    # The gated fetch cannot have completed yet (we control its release below), so receiving
    # ANY frame here proves telemetry streamed while the run was still blocked mid-flight —
    # the batch-at-end alternative could not produce a frame before we release the gate.
    assert not gate.is_set()
    assert not isinstance(first, Completed)

    gate.set()
    frames: list[object] = [first]
    async for frame in gen:
        frames.append(frame)

    last = frames[-1]
    assert isinstance(last, Completed)
    assert "FAST" in last.result.body
    assert "GATED" in last.result.body


# --- 3. ParseError propagates unwrapped, no Completed ------------------------------------------


@pytest.mark.asyncio
async def test_parse_error_raises_unwrapped_with_no_completed() -> None:
    io = StaticIOLayer()
    executor = Url4Executor(io)

    frames: list[ExecStep] = []
    with pytest.raises(ParseError) as exc_info:
        async for frame in executor.execute("((("):
            frames.append(frame)

    assert not isinstance(exc_info.value, ExceptionGroup)
    assert exc_info.value.code == "malformed_source"
    assert exc_info.value.permanent is True
    assert not any(isinstance(f, Completed) for f in frames)


# --- 4. N usage reports sum into the subtree cost ----------------------------------------------


class _UsageChildNode:
    """A hand-built node reporting usage — the mechanism ``test_observe.py`` uses."""

    deps: dict = {}

    async def resolve(self, inputs, ctx) -> str:
        ctx.report_usage(provider="anthropic", model="claude-x", input_tokens=10, output_tokens=5)
        return "child"


class _UsageRootNode:
    """Depends on the child, and ALSO reports usage itself — proves summation across N reports."""

    def __init__(self) -> None:
        self.deps = {"c": _UsageChildNode()}

    async def resolve(self, inputs, ctx) -> str:
        ctx.report_usage(provider="anthropic", model="claude-y", input_tokens=20, output_tokens=8)
        return f"root:{inputs['c']}"


@pytest.mark.asyncio
async def test_n_usage_reports_sum_into_subtree_cost() -> None:
    executor = Url4Executor(StaticIOLayer())

    frames = await _drain(executor, _UsageRootNode())

    completed = frames[-1]
    assert isinstance(completed, Completed)
    usage = completed.subtree_cost.usage
    assert usage.input_tokens == 30  # 10 (child) + 20 (root)
    assert usage.output_tokens == 13  # 5 (child) + 8 (root)
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0
    assert usage.reasoning_tokens == 0
    cost = completed.subtree_cost.cost
    assert cost.input_usd == cost.output_usd == cost.cache_read_usd == 0
    assert cost.cache_creation_usd == cost.reasoning_usd == 0
    assert cost.total_usd == 0
    assert completed.subtree_cost.pricing_version == "unpriced"


# --- 5. zero usage reports still yields an all-zero, valid subtree CostUsage -------------------


@pytest.mark.asyncio
async def test_zero_usage_still_yields_valid_all_zero_subtree() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    executor = Url4Executor(io)

    frames = await _drain(executor, "https://a!go")

    completed = frames[-1]
    assert isinstance(completed, Completed)
    subtree = completed.subtree_cost
    assert subtree.usage.input_tokens == 0
    assert subtree.usage.output_tokens == 0
    assert subtree.cost.total_usd == 0
    assert subtree.pricing_version == "unpriced"
    assert subtree.provider and subtree.model  # non-nullable sentinels, not empty


# --- 5b. F3: subtree provider/model — one shared pair, vs. mixed pairs -------------------------


class _SingleProviderModelNode:
    """Reports usage twice with the SAME (provider, model) pair — the F3 "one pair" case."""

    deps: dict = {}

    async def resolve(self, inputs, ctx) -> str:
        ctx.report_usage(provider="anthropic", model="claude-x", input_tokens=1, output_tokens=1)
        ctx.report_usage(provider="anthropic", model="claude-x", input_tokens=2, output_tokens=2)
        return "ok"


@pytest.mark.asyncio
async def test_subtree_provider_model_when_all_usage_shares_one_pair() -> None:
    executor = Url4Executor(StaticIOLayer())

    frames = await _drain(executor, _SingleProviderModelNode())

    completed = frames[-1]
    assert isinstance(completed, Completed)
    assert completed.subtree_cost.provider == "anthropic"
    assert completed.subtree_cost.model == "claude-x"


@pytest.mark.asyncio
async def test_subtree_provider_model_is_mixed_when_pairs_differ() -> None:
    # _UsageRootNode (test 4 above) reports anthropic/claude-y at the root and anthropic/claude-x
    # at the child — the (provider, model) PAIRS differ, so F3 reports "mixed"/"mixed" rather than
    # an arbitrary last-wins choice between the two.
    executor = Url4Executor(StaticIOLayer())

    frames = await _drain(executor, _UsageRootNode())

    completed = frames[-1]
    assert isinstance(completed, Completed)
    assert completed.subtree_cost.provider == "mixed"
    assert completed.subtree_cost.model == "mixed"


# --- 6. closing the generator cancels the in-flight engine run ---------------------------------


@pytest.mark.asyncio
async def test_closing_generator_cancels_in_flight_engine_run() -> None:
    gate = asyncio.Event()
    released_ran = False

    async def gated(_context: str, _intent: str) -> str:
        nonlocal released_ran
        await gate.wait()
        released_ran = True  # must NEVER execute — the run is cancelled before the gate opens
        return "GATED"

    io = StaticIOLayer(
        fetch_map={"https://fast": "FAST"},
        routes={"/gated": gated},
    )
    executor = Url4Executor(io)
    gen = executor.execute("(f=https://fast, g=/gated()!go)!'$f $g'")

    await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    # WHY the cast: `Executor.execute` (a Protocol method) is typed `AsyncIterator[ExecStep]`,
    # which has no `aclose()` — the concrete object is an async generator at runtime (`execute`
    # is defined with `yield`), so the cast documents that early-close is exercised deliberately.
    await cast("AsyncGenerator[ExecStep, None]", gen).aclose()
    # Give the cancelled task's finally/cleanup a turn on the loop before asserting.
    await asyncio.sleep(0)

    assert released_ran is False
    gate.set()  # nothing left to observe it — release only to avoid leaking a pending waiter


# --- 6b. world_aclose teardown hook (Batch 3, plan §5.3): runs exactly once per execute() call,
# on every exit path (success, error, early aclose), and never masks the run's real outcome. -----


class _AcloseSpy:
    """Records how many times it was awaited (and, optionally, raises on call)."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.calls = 0
        self._raises = raises

    async def __call__(self) -> None:
        self.calls += 1
        if self._raises is not None:
            raise self._raises


@pytest.mark.asyncio
async def test_world_aclose_runs_once_after_a_normal_drain() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    spy = _AcloseSpy()
    executor = Url4Executor(io, world_aclose=spy)

    frames = await _drain(executor, "https://a!go")

    assert isinstance(frames[-1], Completed)
    assert spy.calls == 1


@pytest.mark.asyncio
async def test_world_aclose_runs_once_when_the_run_raises() -> None:
    io = StaticIOLayer()
    spy = _AcloseSpy()
    executor = Url4Executor(io, world_aclose=spy)

    with pytest.raises(ParseError):
        async for _ in executor.execute("((("):
            pass

    assert spy.calls == 1


@pytest.mark.asyncio
async def test_world_aclose_runs_once_on_early_generator_aclose() -> None:
    gate = asyncio.Event()

    async def gated(_context: str, _intent: str) -> str:
        await gate.wait()
        return "GATED"

    io = StaticIOLayer(routes={"/gated": gated})
    spy = _AcloseSpy()
    executor = Url4Executor(io, world_aclose=spy)
    gen = executor.execute("/gated()!go")

    await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    await cast("AsyncGenerator[ExecStep, None]", gen).aclose()
    await asyncio.sleep(0)

    assert spy.calls == 1
    gate.set()  # nothing left to observe it — release only to avoid leaking a pending waiter


@pytest.mark.asyncio
async def test_world_aclose_failure_does_not_mask_the_run_s_real_error() -> None:
    io = StaticIOLayer()
    spy = _AcloseSpy(raises=RuntimeError("teardown boom"))
    executor = Url4Executor(io, world_aclose=spy)

    # The engine's ParseError must still be what propagates — not the teardown's RuntimeError.
    with pytest.raises(ParseError):
        async for _ in executor.execute("((("):
            pass

    assert spy.calls == 1


@pytest.mark.asyncio
async def test_no_world_aclose_is_a_no_op() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    executor = Url4Executor(io)  # world_aclose defaults to None

    frames = await _drain(executor, "https://a!go")

    assert isinstance(frames[-1], Completed)


# --- 7. queue overflow drops only Log events, reports dropped_events WARN Log ------------------


def test_bridge_on_event_drop_policy_never_drops_span_usage_lifecycle() -> None:
    bridge = _Bridge(maxsize=2)
    bridge.on_event(RunStarted("t" * 32, "s" * 16, "hash"))
    bridge.on_event(NodeStarted("span-1", None, "WebFetchNode", ""))
    # Buffer is now full (2/2, both lifecycle) — an incoming Log is dropped outright.
    bridge.on_event(Log("span-1", "INFO", "line-1"))
    bridge.on_event(Log("span-1", "INFO", "line-2"))
    assert bridge.dropped == 2
    assert len(bridge._buf) == 2

    # A lifecycle event with no Log present to evict soft-caps over the limit rather than
    # dropping Span/Usage/lifecycle data.
    bridge.on_event(NodeFinished("span-1", "ok", 1))
    assert bridge.dropped == 2
    assert len(bridge._buf) == 3

    # Now seed one Log so a subsequent lifecycle event evicts it instead of soft-capping.
    bridge2 = _Bridge(maxsize=2)
    bridge2.on_event(NodeStarted("span-1", None, "WebFetchNode", ""))
    bridge2.on_event(Log("span-1", "INFO", "kept-until-evicted"))
    bridge2.on_event(NodeFinished("span-1", "ok", 1))  # evicts the Log to make room
    assert bridge2.dropped == 1
    kinds = [type(e).__name__ for e in bridge2._buf]
    assert "Log" not in kinds
    assert "NodeFinished" in kinds


def test_bridge_raises_on_a_span_only_burst_past_the_hard_cap() -> None:
    # Regression: a burst of lifecycle/Span events with NO Log present to evict must not grow
    # the buffer without limit — past `_hard_cap` (maxsize * _HARD_CAP_MULTIPLIER) it must fail
    # loud instead of soft-capping forever.
    bridge = _Bridge(maxsize=2)
    bridge.on_event(RunStarted("t" * 32, "s" * 16, "hash"))
    bridge.on_event(NodeStarted("span-1", None, "WebFetchNode", ""))
    with pytest.raises(BridgeOverflowError):
        for i in range(bridge._hard_cap):
            bridge.on_event(NodeStarted(f"span-{i}", None, "WebFetchNode", ""))


class _LoggyNode:
    """Emits many Log events synchronously (no ``await`` between them) so they queue up in the
    bridge's buffer before the consumer ever gets a scheduling turn — deterministic overflow,
    no wall-clock sleep required."""

    deps: dict = {}

    async def resolve(self, inputs, ctx) -> str:
        for i in range(20):
            ctx.log("INFO", f"line-{i}")
        return "done"


@pytest.mark.asyncio
async def test_overflow_drops_only_logs_and_reports_dropped_count() -> None:
    executor = Url4Executor(StaticIOLayer(), queue_cap=2)

    frames = await _drain(executor, _LoggyNode())

    completed = frames[-1]
    assert isinstance(completed, Completed)
    assert completed.result.body == "done"

    spans = [f for f in frames if isinstance(_unwrap(f), SpanData)]
    assert len(spans) >= 1  # the node's own span survived the overflow

    warn_logs = [
        f
        for f in frames
        if isinstance(payload := _unwrap(f), LogData)
        and payload.severity_text == "WARN"
        and "dropped" in payload.body
    ]
    assert len(warn_logs) == 1
    # Far fewer surviving INFO logs than the 20 emitted — most were dropped by the tiny cap.
    info_logs = [
        f
        for f in frames
        if isinstance(payload := _unwrap(f), LogData) and payload.severity_text == "INFO"
    ]
    assert len(info_logs) < 20


# --- 7b. a surviving Log passes through as LogData (the overflow test above only exercises the
# drop path — this exercises the normal, non-dropped mapping) ---------------------------------


class _WarningNode:
    deps: dict = {}

    async def resolve(self, inputs, ctx) -> str:
        ctx.log("WARN", "custom warning")
        return "ok"


@pytest.mark.asyncio
async def test_surviving_log_event_maps_to_log_data() -> None:
    executor = Url4Executor(StaticIOLayer())  # default queue_cap: nothing gets dropped

    frames = await _drain(executor, _WarningNode())

    logs = [
        f
        for f in frames
        if isinstance(payload := _unwrap(f), LogData) and payload.body == "custom warning"
    ]
    assert len(logs) == 1
    log = _unwrap(logs[0])
    assert isinstance(log, LogData)
    assert log.severity_number == 13
    assert log.severity_text == "WARN"
    assert isinstance(logs[0], Traced) and logs[0].span is None


# --- 7c. an over-cap result is truncated to `result_cap` bytes with a marker (D5) --------------


class _LongResultNode:
    deps: dict = {}

    async def resolve(self, inputs, ctx) -> str:
        return "X" * 50


@pytest.mark.asyncio
async def test_over_cap_result_is_truncated_with_marker() -> None:
    executor = Url4Executor(StaticIOLayer(), result_cap=20)

    frames = await _drain(executor, _LongResultNode())

    completed = frames[-1]
    assert isinstance(completed, Completed)
    assert completed.result.body.endswith("…[truncated]")
    assert completed.result.body.startswith("X")
    assert len(completed.result.body.encode("utf-8")) <= 20


# --- deny_by_default_world(): the locked-down world __main__.py wires ---------------------------


@pytest.mark.asyncio
async def test_deny_by_default_world_serves_no_routes_or_data() -> None:
    world = deny_by_default_world()
    with pytest.raises(ResolutionError):
        await world.fetch("https://anything", relative=False)


# --- 8. unregistered RelUrl route -> ResolutionError propagates, no crash/hang -----------------


@pytest.mark.asyncio
async def test_unregistered_relurl_route_raises_resolution_error() -> None:
    io = StaticIOLayer()  # no routes, no fetch_map
    executor = Url4Executor(io)

    with pytest.raises(ResolutionError) as exc_info:
        async for _frame in executor.execute("/claude()!go"):
            pass

    assert exc_info.value.code == "resolution_failed"


# --- 9. integration: publish.run publishes the exact §8 frame-type order -----------------------


@pytest.mark.asyncio
async def test_publish_run_orders_frames_per_spec_section_8() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    bus = InMemoryBus()
    topic = "url4-executor-integration"

    await publish_run(bus, Url4Executor(io), topic, "https://a!go")

    frames = []

    async def _collect() -> None:
        async for frame in bus.subscribe(topic, from_sequence=1):
            frames.append(frame)
            if isinstance(frame, TerminatedEvent):
                return

    await asyncio.wait_for(_collect(), timeout=2.0)

    assert isinstance(frames[0], StartedEvent)
    assert isinstance(frames[-1], TerminatedEvent)
    assert frames[-1].data.status == "succeeded"

    # Everything between Started and the final CostUsage{subtree}/Result/Terminated tail is
    # Log/Span/CostUsage{self}, in any order/count ("as available").
    tail_types = [type(f).__name__ for f in frames[-3:-1]]
    assert tail_types == ["CostUsageEvent", "ResultEvent"]
    subtree_frame = frames[-3]
    assert subtree_frame.data.scope == "subtree"

    for frame in frames[1:-3]:
        assert type(frame).__name__ in {"LogEvent", "SpanEvent", "CostUsageEvent"}
        if type(frame).__name__ == "CostUsageEvent":
            assert frame.data.scope == "self"


# --- 10. import isolation (C6): only the 2 allowed modules import url4 -------------------------


def _imports_url4(py_file: Path) -> bool:
    tree = ast.parse(py_file.read_text(), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "url4" or alias.name.startswith("url4.") for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "url4" or node.module.startswith("url4."):
                return True
    return False


# dec:L (plan §2/§5.2) — the connector lives inside url4-cloud, so C6 widens from a
# single-file to a 2-file allowlist rather than staying a reusable standalone package.
_ALLOWED_URL4_IMPORTERS = frozenset({"url4_executor.py", "aigateway_connector.py"})


def test_only_url4_executor_module_imports_url4() -> None:
    offenders = [
        py_file
        for py_file in _SRC_ROOT.rglob("*.py")
        if _imports_url4(py_file) and py_file.name not in _ALLOWED_URL4_IMPORTERS
    ]
    assert offenders == []

    allowed = {
        py_file.name
        for py_file in _SRC_ROOT.rglob("*.py")
        if py_file.name in _ALLOWED_URL4_IMPORTERS and _imports_url4(py_file)
    }
    assert allowed == _ALLOWED_URL4_IMPORTERS
