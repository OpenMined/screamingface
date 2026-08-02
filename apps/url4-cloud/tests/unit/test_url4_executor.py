from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest

from url4.core.errors import ParseError, ResolutionError
from url4.io.static import StaticIOLayer
from url4.observe import Log, NodeFinished, NodeStarted, RunStarted, Usage
from url4.streaming.interfaces import Completed, ExecStep, Traced
from url4.streaming.lifecycle import run as publish_run
from url4.streaming.protocol import (
    CostUsageData,
    LogData,
    SpanData,
    StartedEvent,
    TerminatedEvent,
)
from url4_cloud.runner.executor import (
    BridgeOverflowError,
    Url4Executor,
    _Bridge,
    _RunState,
    deny_by_default_world,
)
from url4_cloud.testing import InMemoryEventStream

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _unwrap(frame: object) -> object:
    return frame.payload if isinstance(frame, Traced) else frame


async def _drain(executor: Url4Executor, url4: object) -> list[object]:
    return [frame async for frame in executor.execute(cast("str", url4))]


@pytest.mark.asyncio
async def test_static_world_yields_span_then_completed_with_real_result() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    executor = Url4Executor(io)

    frames = await _drain(executor, "https://a!go")

    last = frames[-1]
    assert isinstance(last, Completed)
    assert last.result.body == "go\n\nA"
    spans = [f for f in frames[:-1] if isinstance(_unwrap(f), SpanData)]
    assert len(spans) >= 1
    assert all(isinstance(f, Traced) and f.span is not None for f in spans)


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


class _UsageChildNode:
    deps: dict = {}

    async def resolve(self, inputs, ctx) -> str:
        ctx.report_usage(provider="anthropic", model="claude-x", input_tokens=10, output_tokens=5)
        return "child"


class _UsageRootNode:
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
    assert usage.input_tokens == 30
    assert usage.output_tokens == 13
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0
    assert usage.reasoning_tokens == 0
    cost = completed.subtree_cost.cost
    assert cost.input_usd == cost.output_usd == cost.cache_read_usd == 0
    assert cost.cache_creation_usd == cost.reasoning_usd == 0
    assert cost.total_usd == 0
    assert completed.subtree_cost.pricing_version == "unpriced"


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
    assert subtree.provider and subtree.model


class _SingleProviderModelNode:
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
    executor = Url4Executor(StaticIOLayer())

    frames = await _drain(executor, _UsageRootNode())

    completed = frames[-1]
    assert isinstance(completed, Completed)
    assert completed.subtree_cost.provider == "mixed"
    assert completed.subtree_cost.model == "mixed"


@pytest.mark.asyncio
async def test_closing_generator_cancels_in_flight_engine_run() -> None:
    gate = asyncio.Event()
    released_ran = False

    async def gated(_context: str, _intent: str) -> str:
        nonlocal released_ran
        await gate.wait()
        released_ran = True
        return "GATED"

    io = StaticIOLayer(
        fetch_map={"https://fast": "FAST"},
        routes={"/gated": gated},
    )
    executor = Url4Executor(io)
    gen = executor.execute("(f=https://fast, g=/gated()!go)!'$f $g'")

    await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    await cast("AsyncGenerator[ExecStep, None]", gen).aclose()
    await asyncio.sleep(0)

    assert released_ran is False
    gate.set()


class _AcloseSpy:
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
    gate.set()


@pytest.mark.asyncio
async def test_world_aclose_failure_does_not_mask_the_run_s_real_error() -> None:
    io = StaticIOLayer()
    spy = _AcloseSpy(raises=RuntimeError("teardown boom"))
    executor = Url4Executor(io, world_aclose=spy)

    with pytest.raises(ParseError):
        async for _ in executor.execute("((("):
            pass

    assert spy.calls == 1


@pytest.mark.asyncio
async def test_no_world_aclose_is_a_no_op() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    executor = Url4Executor(io)

    frames = await _drain(executor, "https://a!go")

    assert isinstance(frames[-1], Completed)


def test_bridge_on_event_drop_policy_never_drops_span_usage_lifecycle() -> None:
    bridge = _Bridge(maxsize=2)
    bridge.on_event(RunStarted("t" * 32, "s" * 16, "hash"))
    bridge.on_event(NodeStarted("span-1", None, "WebFetchNode", ""))
    bridge.on_event(Log("span-1", "INFO", "line-1"))
    bridge.on_event(Log("span-1", "INFO", "line-2"))
    assert bridge.dropped == 2
    assert len(bridge._buf) == 2

    bridge.on_event(NodeFinished("span-1", "ok", 1))
    assert bridge.dropped == 2
    assert len(bridge._buf) == 3

    bridge2 = _Bridge(maxsize=2)
    bridge2.on_event(NodeStarted("span-1", None, "WebFetchNode", ""))
    bridge2.on_event(Log("span-1", "INFO", "kept-until-evicted"))
    bridge2.on_event(NodeFinished("span-1", "ok", 1))
    assert bridge2.dropped == 1
    kinds = [type(e).__name__ for e in bridge2._buf]
    assert "Log" not in kinds
    assert "NodeFinished" in kinds


def test_bridge_raises_on_a_span_only_burst_past_the_hard_cap() -> None:
    bridge = _Bridge(maxsize=2)
    bridge.on_event(RunStarted("t" * 32, "s" * 16, "hash"))
    bridge.on_event(NodeStarted("span-1", None, "WebFetchNode", ""))
    with pytest.raises(BridgeOverflowError):
        for i in range(bridge._hard_cap):
            bridge.on_event(NodeStarted(f"span-{i}", None, "WebFetchNode", ""))


class _LoggyNode:
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
    assert len(spans) >= 1

    warn_logs = [
        f
        for f in frames
        if isinstance(payload := _unwrap(f), LogData)
        and payload.severity_text == "WARN"
        and "dropped" in payload.body
    ]
    assert len(warn_logs) == 1
    info_logs = [
        f
        for f in frames
        if isinstance(payload := _unwrap(f), LogData) and payload.severity_text == "INFO"
    ]
    assert len(info_logs) < 20


class _WarningNode:
    deps: dict = {}

    async def resolve(self, inputs, ctx) -> str:
        ctx.log("WARN", "custom warning")
        return "ok"


@pytest.mark.asyncio
async def test_surviving_log_event_maps_to_log_data() -> None:
    executor = Url4Executor(StaticIOLayer())

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
    # A log emitted from inside a node is attributed to THAT node's span, not to the run root.
    # This assertion used to require `span is None`, which pinned the defect: the engine supplies
    # `Log.span_id`, the executor discarded it, and every log line on the wire looked as though it
    # came from the run itself — so no consumer could tell which node logged what.
    assert isinstance(logs[0], Traced)
    assert logs[0].span is not None
    span_ids = {
        f.span.span_id
        for f in frames
        if isinstance(f, Traced) and f.span is not None and isinstance(f.payload, SpanData)
    }
    assert logs[0].span.span_id in span_ids


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


@pytest.mark.asyncio
async def test_deny_by_default_world_serves_no_routes_or_data() -> None:
    world = deny_by_default_world()
    with pytest.raises(ResolutionError):
        await world.fetch("https://anything", relative=False)


@pytest.mark.asyncio
async def test_unregistered_relurl_route_raises_resolution_error() -> None:
    io = StaticIOLayer()
    executor = Url4Executor(io)

    with pytest.raises(ResolutionError) as exc_info:
        async for _frame in executor.execute("/claude()!go"):
            pass

    assert exc_info.value.code == "resolution_failed"


@pytest.mark.asyncio
async def test_publish_run_orders_frames_per_spec_section_8() -> None:
    io = StaticIOLayer(fetch_map={"https://a": "A"})
    stream = InMemoryEventStream()
    topic = "url4-executor-integration"

    await publish_run(stream, Url4Executor(io), topic, "https://a!go")

    frames = []

    async def _collect() -> None:
        async for frame in stream.subscribe(topic, from_sequence=1):
            frames.append(frame)
            if isinstance(frame, TerminatedEvent):
                return

    await asyncio.wait_for(_collect(), timeout=2.0)

    assert isinstance(frames[0], StartedEvent)
    assert isinstance(frames[-1], TerminatedEvent)
    assert frames[-1].data.status == "succeeded"

    tail_types = [type(f).__name__ for f in frames[-3:-1]]
    assert tail_types == ["CostUsageEvent", "ResultEvent"]
    subtree_frame = frames[-3]
    assert subtree_frame.data.scope == "subtree"

    for frame in frames[1:-3]:
        assert type(frame).__name__ in {"LogEvent", "SpanEvent", "CostUsageEvent"}
        if type(frame).__name__ == "CostUsageEvent":
            assert frame.data.scope == "self"


def _is_engine_module(module: str) -> bool:
    """True for the url4 ENGINE surface, false for the wire contract.

    `url4.streaming` ships in the same distribution as the engine but is the protocol vocabulary
    every Runner module is entitled to speak, so it is deliberately not an engine import. Bare
    `url4` IS: its package __init__ re-exports the engine's public API.
    """
    return module == "url4" or (
        module.startswith("url4.") and not module.startswith("url4.streaming")
    )


def _imports_url4_engine(py_file: Path) -> bool:
    tree = ast.parse(py_file.read_text(), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            _is_engine_module(alias.name) for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if _is_engine_module(node.module):
                return True
    return False


def _url4_engine_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(), filename=str(py_file))
    selected: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            selected.update(alias.name for alias in node.names if _is_engine_module(alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if _is_engine_module(node.module):
                selected.add(node.module)
    return selected


_ALLOWED_URL4_IMPORTERS = frozenset({"executor.py", "connector.py"})


def _is_benchmark_author(py_file: Path) -> bool:
    return "benchmarks" in py_file.relative_to(_SRC_ROOT).parts


def test_only_runner_adapters_and_benchmark_authors_import_url4() -> None:
    """Execution stays in two adapters; Benchmark authors may construct public URL4 ASTs.

    `url4.streaming` is exempt — it is the wire contract, which both halves speak. This scans
    the whole distribution now rather than a separate runner tree: merging the two packages
    means the control-plane modules are in scope too. Engine-owned Benchmark definitions are the
    one deliberate construction boundary: authors use URL4's public typed AST and server API to
    install their private runtime, while execution remains confined to Runner-owned worlds.
    """
    offenders = [
        py_file
        for py_file in _SRC_ROOT.rglob("*.py")
        if _imports_url4_engine(py_file)
        and py_file.name not in _ALLOWED_URL4_IMPORTERS
        and not _is_benchmark_author(py_file)
    ]
    assert offenders == []

    allowed = {
        py_file.name
        for py_file in _SRC_ROOT.rglob("*.py")
        if py_file.name in _ALLOWED_URL4_IMPORTERS and _imports_url4_engine(py_file)
    }
    assert allowed == _ALLOWED_URL4_IMPORTERS

    benchmark_imports = {
        module
        for py_file in _SRC_ROOT.rglob("*.py")
        if _is_benchmark_author(py_file)
        for module in _url4_engine_modules(py_file)
    }
    assert benchmark_imports <= {"url4", "url4.core.errors", "url4.peer.server"}


# --- per-span usage accumulation ---------------------------------------------------------

_SPAN = "0123456789abcdef"


def _usage(input_tokens: int, output_tokens: int) -> Usage:
    return Usage(
        span_id=_SPAN,
        provider="openrouter",
        model="m",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _one_node_two_usage_events() -> tuple[SpanData, CostUsageData, CostUsageData]:
    """Drive `_RunState` through ONE node that reports usage TWICE.

    This is the ordinary shape of a `web_tools` route, not a corner case: every aigateway round
    trip in the tool loop reports its own usage against the same span.
    """
    state = _RunState()
    state.map(NodeStarted(span_id=_SPAN, parent_span_id=None, node_kind="RelUrlNode", detail="m"))
    state.map(_usage(124, 10))
    state.map(_usage(3558, 20))
    frames = state.map(NodeFinished(span_id=_SPAN, status="ok", engine_seq=1))
    span = next(f.payload for f in frames if isinstance(f.payload, SpanData))
    self_cost = next(
        f.payload
        for f in frames
        if isinstance(f.payload, CostUsageData) and f.payload.scope == "self"
    )
    return span, self_cost, state.build_subtree()


def test_a_span_accumulates_usage_across_every_report() -> None:
    # Regression: this used to ASSIGN, keeping only the final round trip.
    span, _, _ = _one_node_two_usage_events()

    assert (span.input_tokens, span.output_tokens) == (3682, 30)


def test_self_scope_cost_accumulates_usage_across_every_report() -> None:
    _, self_cost, _ = _one_node_two_usage_events()

    assert (self_cost.usage.input_tokens, self_cost.usage.output_tokens) == (3682, 30)


def test_self_and_subtree_agree_when_the_run_is_a_single_node() -> None:
    # The invariant the bug broke: per-node cost that under-reports against a run total that
    # does not is worse than either being wrong alone — they are reconciled against each other.
    _, self_cost, subtree = _one_node_two_usage_events()

    assert self_cost.usage.input_tokens == subtree.usage.input_tokens
    assert self_cost.usage.output_tokens == subtree.usage.output_tokens
