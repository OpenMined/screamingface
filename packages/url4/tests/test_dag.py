"""The DAG capabilities: scheduling, memoization, laziness, extensibility."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import RecordingIOLayer

from url4.dag import (
    DEFAULT_MAP_CONCURRENCY,
    BarrierNode,
    BindingNode,
    ExecutionContext,
    JoinNode,
    LazyExprNode,
    MapNode,
    ProcessNode,
    RelUrlNode,
    TextNode,
    WebFetchNode,
    compile_expression,
    default_registry,
    run,
)
from url4.errors import CycleError, ParseError, ResolutionError
from url4.io_static import StaticIOLayer
from url4.nodes import ForeachDirectives, Text, Url


class BarrierIOLayer:
    """Releases fetches only once ``expected`` of them are in flight at once."""

    def __init__(self, expected: int) -> None:
        self._expected = expected
        self._in_flight: set[str] = set()
        self._all_started = asyncio.Event()

    async def fetch(self, target: str, *, relative: bool) -> str:
        self._in_flight.add(target)
        if len(self._in_flight) >= self._expected:
            self._all_started.set()
        await asyncio.wait_for(self._all_started.wait(), timeout=2)
        return target.rsplit("/", 1)[-1].upper()


@pytest.mark.asyncio
async def test_independent_sources_fetch_in_parallel() -> None:
    # Each fetch blocks until BOTH are in flight — only true parallelism passes.
    resolver = BarrierIOLayer(expected=2)
    result = await run("(https://host/a, https://host/b)!go", resolver)
    assert result == "go\n\nA\nB"


@pytest.mark.asyncio
async def test_global_concurrency_bound_caps_bare_fanout() -> None:
    # C1: run()'s global concurrency bound must cap a bare fan-out group's
    # independent sources, not just MapNode rows (which only have a node-local
    # cap). 8 sources, bound to 2 in flight at once.
    in_flight = 0
    seen_max = 0

    class CountingIOLayer:
        async def fetch(self, target: str, *, relative: bool) -> str:
            nonlocal in_flight, seen_max
            in_flight += 1
            seen_max = max(seen_max, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return target.rsplit("/", 1)[-1].upper()

    sources = ", ".join(f"https://host/{c}" for c in "abcdefgh")
    await run(f"({sources})!go", CountingIOLayer(), concurrency=2)
    assert seen_max <= 2
    assert seen_max > 1  # still parallel, just bounded — not accidentally serial


@pytest.mark.asyncio
async def test_global_concurrency_bound_holds_across_mixed_fanout_and_map() -> None:
    # C1: the global bound must hold across a SINGLE run mixing a bare fan-out
    # of independent sources with a MapNode's rows — both node kinds fetch
    # through the one run-wide BoundedIOLayer wrapper, so combined in-flight
    # fetches never exceed the global bound even though MapNode's own per-row
    # cap (left at its default here, which is looser) would otherwise allow
    # every row to attempt concurrently.
    in_flight = 0
    seen_max = 0

    class CountingIOLayer:
        async def fetch(self, target: str, *, relative: bool) -> str:
            nonlocal in_flight, seen_max
            in_flight += 1
            seen_max = max(seen_max, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return "x"

    collection = TextNode('["1", "2", "3", "4"]')
    map_node = MapNode(body="https://row/item", deps={"collection": collection})
    graph = JoinNode(
        deps={
            "part:0": WebFetchNode("https://a"),
            "part:1": WebFetchNode("https://b"),
            "part:2": map_node,
        }
    )
    await run(graph, CountingIOLayer(), concurrency=2)
    assert seen_max <= 2
    assert seen_max > 1


@pytest.mark.asyncio
async def test_global_concurrency_bound_can_be_disabled() -> None:
    # concurrency=None is the documented escape hatch back to the pre-existing
    # unbounded behavior. BarrierIOLayer requires BOTH fetches in flight at
    # once — a wrongly-applied low bound would deadlock (and time out) here.
    resolver = BarrierIOLayer(expected=2)
    result = await run("(https://host/a, https://host/b)!go", resolver, concurrency=None)
    assert result == "go\n\nA\nB"


@pytest.mark.asyncio
async def test_run_rejects_zero_concurrency_instead_of_deadlocking() -> None:
    # BUG-1 regression: concurrency=0 used to build asyncio.Semaphore(0), which
    # can never be acquired — every fetch hung forever (no error, no timeout, and
    # the finally/aclose never ran, leaking the owned client). It must now raise
    # a clear ValueError at the run() boundary, before any scheduling.
    resolver = StaticIOLayer(fetch_map={"https://a": "A", "https://b": "B"})
    with pytest.raises(ValueError, match="concurrency.*>= 1"):
        await run("(https://a, https://b)!go", resolver, concurrency=0)


@pytest.mark.asyncio
async def test_run_rejects_negative_concurrency() -> None:
    # Negative concurrency previously surfaced as a raw asyncio ValueError from
    # Semaphore deep in the executor at first-fetch time; it must raise the
    # url4-level guard at the call site instead.
    resolver = StaticIOLayer(fetch_map={"https://a": "A"})
    with pytest.raises(ValueError, match="concurrency.*>= 1"):
        await run("https://a!go", resolver, concurrency=-5)


@pytest.mark.asyncio
async def test_run_rejects_non_int_concurrency() -> None:
    # A non-int (e.g. a str from upstream config) would otherwise reach
    # asyncio.Semaphore and raise a confusing TypeError; guard it at run().
    resolver = StaticIOLayer(fetch_map={"https://a": "A"})
    with pytest.raises(TypeError, match="concurrency.*int"):
        await run("https://a!go", resolver, concurrency="2")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_zero_concurrency_does_not_hang() -> None:
    # The guard fires before BoundedIOLayer is built, so run() returns promptly
    # instead of hanging on a Semaphore(0) that can never be acquired.
    import time

    started = time.monotonic()
    with pytest.raises(ValueError):
        await run("(https://a, https://b)!go", None, concurrency=0)
    assert time.monotonic() - started < 5  # never hangs


@pytest.mark.asyncio
async def test_diamond_binding_resolved_once() -> None:
    # One binding read by two consumers and the intent → a single fetch.
    resolver = RecordingIOLayer(fetch_map={"https://x": "V"})
    result = await run("(a=https://x, use $a, also $a)!both: $a", resolver)
    assert result == "both: V\n\nuse V\nalso V"
    assert resolver.fetches.count("https://x") == 1


@pytest.mark.asyncio
async def test_map_concurrency_bound_respected() -> None:
    in_flight = 0
    seen_max = 0

    async def solve(context: str, intent: str) -> str:
        nonlocal in_flight, seen_max
        in_flight += 1
        seen_max = max(seen_max, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return context

    resolver = StaticIOLayer(
        fetch_map={"https://data": '[{"q": "1"}, {"q": "2"}, {"q": "3"}, {"q": "4"}]'},
        routes={"/solve": solve},
    )
    await run("https://data*(/solve($item.q));iteration.concurrency=2", resolver)
    assert seen_max <= 2


@pytest.mark.asyncio
async def test_map_default_concurrency_is_bounded() -> None:
    # C2: no `;foreach.concurrency` directive must NOT mean "all rows at once".
    # A collection larger than DEFAULT_MAP_CONCURRENCY must still respect it.
    in_flight = 0
    seen_max = 0

    async def solve(context: str, intent: str) -> str:
        nonlocal in_flight, seen_max
        in_flight += 1
        seen_max = max(seen_max, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return context

    rows = [{"q": str(i)} for i in range(DEFAULT_MAP_CONCURRENCY * 3)]
    resolver = StaticIOLayer(
        fetch_map={"https://data": json.dumps(rows)},
        routes={"/solve": solve},
    )
    await run("https://data*(/solve($item.q))", resolver)
    assert seen_max <= DEFAULT_MAP_CONCURRENCY
    assert seen_max > 1  # still parallel, just bounded — not accidentally serial


@pytest.mark.asyncio
async def test_map_non_positive_concurrency_falls_back_to_default() -> None:
    # A falsy/non-positive concurrency (only reachable by constructing
    # IterationDirectives directly — the surface `;iteration.concurrency`
    # syntax rejects n < 1) must mean "use the default bound", never "unbounded".
    resolver = StaticIOLayer(fetch_map={"https://data": '["1", "2"]'})
    graph = compile_expression("https://data*($item)")
    map_node = graph.sink.deps["rows"]
    assert isinstance(map_node, MapNode)
    map_node.directives = ForeachDirectives(concurrency=0)
    result = await run(graph, resolver)
    assert json.loads(result) == ["1", "2"]


@pytest.mark.asyncio
async def test_abort_cancels_sibling_rows() -> None:
    slow_started = asyncio.Event()
    slow_cancelled = asyncio.Event()

    async def solve(context: str, intent: str) -> str:
        if context == "bad":
            await asyncio.wait_for(slow_started.wait(), timeout=2)
            raise RuntimeError("boom")
        slow_started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            slow_cancelled.set()
            raise
        return context

    resolver = StaticIOLayer(
        fetch_map={"https://data": '[{"q": "slow"}, {"q": "bad"}]'},
        routes={"/solve": solve},
    )
    with pytest.raises(RuntimeError, match="boom"):
        await run("https://data*(/solve($item.q));iteration.on_error=fail", resolver)
    assert slow_cancelled.is_set()


class ShoutNode:
    """A custom node: satisfies the DagNode protocol with no inheritance."""

    def __init__(self, inner) -> None:
        self._deps: dict = {"inner": inner}

    @property
    def deps(self):
        return self._deps

    async def resolve(self, inputs, ctx) -> str:
        value = inputs["inner"]
        return (value if isinstance(value, str) else "\n".join(value)).upper()


@pytest.mark.asyncio
async def test_custom_node_in_hand_built_graph() -> None:
    node = ShoutNode(TextNode("hello world"))
    assert await run(node, RecordingIOLayer()) == "HELLO WORLD"


@pytest.mark.asyncio
async def test_cycle_detected_before_any_resolve() -> None:
    a = ShoutNode(TextNode("x"))
    b = ShoutNode(a)
    a._deps["back"] = b  # forge a cycle
    with pytest.raises(CycleError):
        await run(b, RecordingIOLayer())


@pytest.mark.asyncio
async def test_lowering_registry_override() -> None:
    class CachedNode:
        deps: dict = {}

        async def resolve(self, inputs, ctx) -> str:
            return "CACHED"

    registry = default_registry()
    registry.register(Url, lambda node, edges, reg: CachedNode())
    result = await run("https://x!go", RecordingIOLayer(), registry=registry)
    assert result == "go\n\nCACHED"


def test_collect_captures_errors_but_propagates_cancellation() -> None:
    node = MapNode(body="x")
    ctx = ExecutionContext(StaticIOLayer())
    # A regular error is captured as a per-row data result...
    out = node._collect([ResolutionError("boom"), "ok"], ctx)
    assert ctx.collected_errors == 1
    assert '"error"' in out[0] and out[1] == "ok"
    # ...but a CancelledError is a control-flow signal, never a row: it propagates.
    with pytest.raises(asyncio.CancelledError):
        node._collect([asyncio.CancelledError()], ctx)


@pytest.mark.asyncio
async def test_validate_uses_graph_registry_for_lazy_fragments() -> None:
    class Marker(Exception):
        pass

    def boom(node, edges, reg):
        raise Marker()

    registry = default_registry()
    registry.register(Url, boom)
    # The nested group defers to a LazyExprNode, so the custom (raising) Url
    # lowering isn't reached at outer compile...
    graph = compile_expression("(a, (https://x, https://z)!y)!go", registry=registry)
    # ...but validate() must expand it with the graph's own registry, not the
    # default — reaching boom. (Old behavior compiled with default_registry and
    # silently validated an expression using the custom form.)
    with pytest.raises(Marker):
        graph.validate()


def test_nested_group_compiles_to_lazy_thunk() -> None:
    graph = compile_expression("(a, (nested, stuff)!x)!go")
    lazies = [node for node in graph.walk() if isinstance(node, LazyExprNode)]
    assert [lazy.text for lazy in lazies] == ["(nested, stuff)!x"]


@pytest.mark.asyncio
async def test_malformed_nested_fragment_errors_only_at_execution() -> None:
    # The nested group's inner text is invalid url4 — compile defers it...
    graph = compile_expression("(a, ((b)(c))!x)!go")
    # ...validate() forces expansion and fails fast...
    with pytest.raises(ParseError):
        graph.validate()
    # ...and executing reaches the thunk and raises the same error.
    with pytest.raises(ParseError):
        await run(graph, RecordingIOLayer())


def test_graph_shape_for_mixed_group() -> None:
    graph = compile_expression("(a=x, /c()!go)!m")
    sink = graph.sink
    assert isinstance(sink, ProcessNode)
    assert list(sink.deps) == ["src:0", "src:1"]
    assert isinstance(sink.deps["src:0"], BindingNode)
    # A text intent is ProcessNode's template, substituted against the
    # populated post-gather scope (expansion renumbers $N there — §5.3.12.4).
    assert sink.intent_template == "m"
    assert sink.slots == (("a", True), (None, False))


@pytest.mark.asyncio
async def test_explicit_context_reports_collected_errors() -> None:
    resolver = StaticIOLayer(
        fetch_map={"https://data": '[{"q": "ok"}, {"other": "bad"}]'},
        routes={"/solve": lambda context, intent: context},
    )
    ctx = ExecutionContext(resolver, strict_fields=True)
    await run("https://data*(/solve($item.q))", ctx=ctx)
    assert ctx.collected_errors == 1


@pytest.mark.asyncio
async def test_shared_ctx_across_concurrent_runs_gets_independent_spawn_wiring() -> None:
    # C4: run() must not mutate a caller-supplied ctx's spawn wiring in place —
    # two overlapping run() calls sharing one ctx, each with its own registry,
    # must each spawn MapNode rows through their OWN registry, not whichever one
    # wired last. This is the regression test for the ctx.spawn logical race.
    resolver = StaticIOLayer(fetch_map={"https://data": '["1"]'})
    ctx = ExecutionContext(resolver)

    def _make_registry(prefix: str):
        registry = default_registry()

        def _lower_text_prefixed(node, edges, _registry):
            assert isinstance(node, Text)
            return TextNode(f"{prefix}{node.value}", deps=dict(edges))

        registry.register(Text, _lower_text_prefixed)
        return registry

    # "row $item" parses as a Text atom (a standalone "$item" is a VarRef and
    # would bypass the custom Text lowering this test observes).
    result_a, result_b = await asyncio.gather(
        run("https://data*(row $item)", ctx=ctx, registry=_make_registry("A:")),
        run("https://data*(row $item)", ctx=ctx, registry=_make_registry("B:")),
    )
    assert json.loads(result_a) == ["A:row 1"]
    assert json.loads(result_b) == ["B:row 1"]


@pytest.mark.asyncio
async def test_run_rejects_ctx_combined_with_io_or_processor_or_process() -> None:
    # F3: ctx already carries io/processor/process; combining silently ignored
    # the other kwargs before this fix. Now it's a hard error.
    resolver = StaticIOLayer(fetch_map={"https://x": "V"})
    ctx = ExecutionContext(resolver)
    with pytest.raises(ValueError, match="ctx.*io.*processor.*process"):
        await run("https://x!go", resolver, ctx=ctx)
    with pytest.raises(ValueError, match="ctx.*io.*processor.*process"):
        await run("https://x!go", ctx=ctx, processor="/other")
    with pytest.raises(ValueError, match="ctx.*io.*processor.*process"):
        await run("https://x!go", ctx=ctx, process=lambda s, i, sc: None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_fetch_intent_over_base_group_uses_barrier_and_merges() -> None:
    # F2: a non-text (fetch) top-level intent over a parenthesised group — an
    # absolute URL or a bare /path — lowers through compiler._base_graph's
    # is_text=False branch (the BarrierNode path), which is otherwise uncovered.
    # Pin the structural contract (a BarrierNode carrying `inner` + `wait:*` deps
    # that ARE the source nodes) and the observable result (the fetched intent
    # merges with the resolved sources via default_process). The barrier is
    # structural: ProcessNode already waits on the sources, so it does not
    # serialize the intent fetch against them — it makes the fetch-intent node
    # structurally depend on every source, matching the reference engine.
    io = RecordingIOLayer(fetch_map={"https://a": "A", "https://b": "B", "https://instr": "INSTR"})
    graph = compile_expression("(https://a, https://b)!https://instr")

    sink = graph.sink
    assert isinstance(sink, ProcessNode)
    intent = sink.deps["intent"]
    assert isinstance(intent, BarrierNode)
    # The barrier's inner is the fetch node; its waits are exactly the sources.
    assert isinstance(intent.deps["inner"], WebFetchNode)
    assert intent.deps["inner"].url == "https://instr"
    assert {intent.deps[f"wait:{i}"] for i in range(2)} == {
        sink.deps["src:0"],
        sink.deps["src:1"],
    }

    # The fetched intent value is merged with the sources, and fetched once.
    result = await run(graph, io)
    assert result == "INSTR\n\nA\nB"
    assert io.fetches.count("https://instr") == 1


@pytest.mark.asyncio
async def test_relative_url_intent_is_a_data_read_through_barrier() -> None:
    # F2: a /path top-level intent classifies as a RelUrl (data read, not an
    # expression), so it ALSO goes through the Barrier path — inner is a
    # RelUrlNode with is_expr=False. Pin that shape so the barrier branch stays
    # covered for the relative-URL form too.
    io = RecordingIOLayer(fetch_map={"https://a": "A", "/doc": "DOC"})
    graph = compile_expression("(https://a)!/doc")
    intent = graph.sink.deps["intent"]
    assert isinstance(intent, BarrierNode)
    inner = intent.deps["inner"]
    assert isinstance(inner, RelUrlNode)
    assert inner.is_expr is False
    result = await run(graph, io)
    assert result == "DOC\n\nA"
