"""The dataflow executor: demand-driven, memoized, structurally concurrent.

One :class:`asyncio.Task` per node per run, keyed by node identity — diamond
dependencies resolve exactly once, and independent nodes run in parallel
simply because their tasks coexist. Execution is pull-based from the sink, so
only reachable nodes are ever scheduled.

Tasks live in one :class:`asyncio.TaskGroup`: the first failure cancels every
in-flight sibling (a deliberate improvement over the reference engine's bare
``gather``, which left siblings running). The group's ``ExceptionGroup`` is
unwrapped back to the first real error so callers keep catching plain
:class:`~url4.errors.Url4Error` subclasses.

Dependency tasks are created (scheduled) in ``deps`` insertion order, which
keeps *dispatch* deterministic — the sequence of ``create_task`` calls. That is
not the same as I/O *completion* order: independent nodes still run in
parallel, so their ``ctx.io.fetch`` calls may arrive at (or return from) the
I/O layer in any interleaving. An order-sensitive ``IOLayer`` must not assume
FIFO arrival.
"""

from __future__ import annotations

import asyncio
from typing import cast

from url4.context import Context
from url4.errors import CycleError
from url4.io_layer import IOLayer
from url4.nodes import Node as AstNode

from url4.dag.compiler import Graph, LoweringRegistry, compile_expression  # isort: skip
from url4.dag.node import (  # isort: skip
    DEFAULT_PROCESSOR,
    DEFAULT_RUN_CONCURRENCY,
    BoundedIOLayer,
    DagNode,
    ExecutionContext,
    Payload,
    ProcessFn,
    SourceFailure,
    default_process,
    first_error,
)
from url4.dag.nodes import GuardNode  # isort: skip


def _dag_children(node: DagNode) -> list[DagNode]:
    """Every node ``node`` executes: its edges, plus a guard's held subtree.

    :class:`GuardNode` holds its inner as an attribute (isolation boundary, not
    an edge), but a cycle through it would still hang the run — the traversals
    here must see it.
    """
    children = list(node.deps.values())
    if isinstance(node, GuardNode):
        children.append(node.inner)
    return children


def check_acyclic(root: DagNode) -> None:
    """Raise :class:`CycleError` if the graph reachable from ``root`` has a cycle.

    Iterative DFS with gray/black coloring. Compiler-emitted graphs are acyclic
    by construction; this guards graphs assembled by hand from custom nodes.
    """
    GRAY, BLACK = 1, 2
    state: dict[int, int] = {}
    stack: list[tuple[DagNode, bool]] = [(root, False)]
    while stack:
        node, leaving = stack.pop()
        if leaving:
            state[id(node)] = BLACK
            continue
        if state.get(id(node)) == BLACK:
            continue
        if state.get(id(node)) == GRAY:
            raise CycleError(f"dependency cycle through {type(node).__name__} node")
        state[id(node)] = GRAY
        stack.append((node, True))
        for dep in _dag_children(node):
            if state.get(id(dep)) != BLACK:
                stack.append((dep, False))


def _validate_concurrency(concurrency: int | None) -> None:
    """Reject a run-wide I/O cap that can't be honored — before any allocation.

    The surface ``;iteration.concurrency`` syntax rejects ``n < 1`` with a
    ParseError; :func:`run`'s programmatic ``concurrency`` kwarg must do the
    same, and BEFORE :class:`BoundedIOLayer` builds an :class:`asyncio.Semaphore`.
    A ``Semaphore(0)`` can never be acquired, so every fetch would hang forever
    (no error, no timeout, and ``run``'s try/finally would never close the owned
    client). A non-int is rejected too so a bad upstream config value surfaces
    here, not as a raw asyncio TypeError at first-fetch time. ``None`` opts out.
    ``bool`` is an ``int`` subclass, so ``True`` (1) is accepted and ``False``
    (0) is rejected — the latter would otherwise hang.
    """
    if concurrency is None:
        return
    if not isinstance(concurrency, int):
        raise TypeError(
            f"run(): `concurrency` must be an int or None (None opts out of the "
            f"run-wide I/O cap); got {type(concurrency).__name__}={concurrency!r}"
        )
    if concurrency < 1:
        raise ValueError(
            "run(): `concurrency` must be >= 1, or None to opt out of the "
            f"run-wide I/O cap; got {concurrency!r}"
        )


class Executor:
    """Executes one graph run against a per-run :class:`ExecutionContext`."""

    def __init__(self, ctx: ExecutionContext) -> None:
        self._ctx = ctx
        # id -> (task, node); the node reference pins the id for the run's lifetime
        self._memo: dict[int, tuple[asyncio.Task, DagNode]] = {}
        self._tg: asyncio.TaskGroup | None = None

    async def execute(self, root: DagNode, *, _prevalidated: bool = False) -> str:
        """Execute ``root`` and render the sink payload as the run's string result.

        A ``list[str]`` sink (a bare hand-built Map/Expand) joins on newlines; a
        tolerated :class:`~url4.dag.node.SourceFailure` sink (a lone optional
        source that failed) renders as the empty result. Compiler-emitted graphs
        end in string-producing sinks, so both cases only arise for hand-built
        graphs.
        """
        result = await self.execute_payload(root, _prevalidated=_prevalidated)
        if isinstance(result, SourceFailure):
            return ""
        return result if isinstance(result, str) else "\n".join(result)

    async def execute_payload(self, root: DagNode, *, _prevalidated: bool = False) -> Payload:
        # Acyclicity is a property of the *graph*, not of the executor, so it is
        # checked once per graph rather than once per ``execute``. The default
        # (``_prevalidated=False``) keeps the guard for graphs assembled by hand
        # from custom nodes (the only graphs that can cycle — compiler-emitted
        # ones are acyclic by construction), pinned by
        # ``test_cycle_detected_before_any_resolve``. The spawn closure validates a
        # compiled fragment once (on first compile) and passes ``True`` so the
        # same memoized graph re-executed once per row / per lazy consumer skips
        # the redundant O(V+E) DFS N times — which would otherwise dwarf the
        # compile it took to get here for large collections.
        if not _prevalidated:
            check_acyclic(root)
        try:
            async with asyncio.TaskGroup() as tg:
                self._tg = tg
                result = await self._run(root)
        except BaseExceptionGroup as group:
            error = first_error(group)
            if error is None:
                raise
            raise error from None
        return result

    async def _run(self, node: DagNode) -> Payload:
        assert self._tg is not None
        # Check-then-act on ``_memo`` is safe ONLY because there is no ``await``
        # between the ``.get()`` and the store below: ``create_task`` schedules
        # without yielding, so on this single-threaded loop the whole block is an
        # atomic critical section. Two parents of a diamond dependency can both
        # call ``_run(shared_child)`` "concurrently", but never interleave here.
        # This is what keeps diamond deps resolving exactly once
        # (test_diamond_binding_resolved_once). Do not insert an ``await`` (a log
        # call, a metric, anything) between the check and the assignment — doing
        # so would let a second caller schedule a duplicate task before the first
        # one lands in ``_memo``, silently resolving a shared node twice.
        memoized = self._memo.get(id(node))
        if memoized is None:
            task = self._tg.create_task(self._eval(node))
            self._memo[id(node)] = memoized = (task, node)
        return await memoized[0]

    async def _eval(self, node: DagNode) -> Payload:
        roles = list(node.deps)  # insertion order → deterministic scheduling
        values = await asyncio.gather(*(self._run(dep) for dep in node.deps.values()))
        return await node.resolve(dict(zip(roles, values, strict=True)), self._ctx)


def _wire_spawn(ctx: ExecutionContext, registry: LoweringRegistry | None) -> None:
    """Bind the dynamic-expansion hook: compile a fragment, run it fresh.

    The compiled :class:`~url4.dag.compiler.Graph` is memoized by its surface
    text for the run's lifetime. Every row of a
    :class:`~url4.dag.nodes.MapNode` spawns the *same* body text (``body`` and
    ``intent`` are node attributes, constant across rows), and every shared
    :class:`~url4.dag.nodes.LazyExprNode` fragment that several consumers pull
    resolves to the same text — so the lowering (``decode_envelope`` →
    recursive-descent parse → graph wiring) runs once per *unique* fragment, not once
    per row. ``registry`` is fixed for the run (captured here), so the text alone
    is a complete cache key; the dict is scoped to this closure and dies with the
    run, so it can neither leak across a long-lived process nor corrupt results
    across runs with different custom lowerings (a module-level cache would do
    both). The compiled graph is pure template data + structural ``deps`` — all
    per-run state lives in the :class:`Executor` / :class:`ExecutionContext` —
    so reusing one graph across N fresh executors (one per row, each on
    ``ctx.child(scope)`` with that row's ``$item`` binding) is safe by
    construction.
    """
    compiled: dict[str, Graph] = {}

    async def spawn(text: str, scope: Context) -> str:
        graph = compiled.get(text)
        if graph is None:
            # Safe under concurrent rows: ``compile_expression`` is synchronous
            # (no ``await``), so the get → compile → store is an atomic critical
            # section on this single-threaded loop — the second row to reach the
            # same text always hits the cache (mirrors the ``_memo`` invariant
            # in ``_run``). A duplicate compile would only be wasted work anyway
            # (same text → an equivalent graph), never a correctness bug.
            graph = compile_expression(text, registry=registry)
            # Acyclicity is a graph property, so validate once per unique
            # fragment, not once per row that re-executes it. Compiler-emitted
            # graphs are acyclic by construction; this single check guards a
            # buggy custom ``LoweringRegistry`` wiring a cycle into a spawned
            # fragment — ``_prevalidated=True`` below then skips the per-row
            # re-check in ``execute`` (which still defaults to checking, for
            # hand-built graphs passed directly to ``run`` / ``execute``).
            check_acyclic(graph.sink)
            compiled[text] = graph
        return await Executor(ctx.child(scope)).execute(graph.sink, _prevalidated=True)

    async def execute_node(node: DagNode, scope: Context) -> Payload:
        # GuardNode's isolation boundary: the prebuilt subtree runs on its own
        # executor (own TaskGroup), so a tolerated failure surfaces to the guard
        # as an exception to convert — never as a sibling-cancelling TaskGroup
        # fault in the outer run. Payload-preserving (no string join): a guarded
        # ExpandNode must deliver its list[str] to the group intact.
        return await Executor(ctx.child(scope)).execute_payload(node, _prevalidated=True)

    ctx.spawn = spawn
    ctx.execute_node = execute_node


def _to_node(target: str | AstNode | Graph | DagNode, registry: LoweringRegistry | None) -> DagNode:
    if isinstance(target, Graph):
        return target.sink
    if isinstance(target, DagNode):  # parse-tree nodes have no resolve → fall through
        return target
    return compile_expression(cast("str | AstNode", target), registry=registry).sink


async def run(
    target: str | AstNode | Graph | DagNode,
    io: IOLayer | None = None,
    *,
    processor: str = DEFAULT_PROCESSOR,
    process: ProcessFn = default_process,
    registry: LoweringRegistry | None = None,
    ctx: ExecutionContext | None = None,
    concurrency: int | None = DEFAULT_RUN_CONCURRENCY,
    strict_fields: bool = False,
) -> str:
    """Evaluate a url4 expression (text, parse tree, graph, or node) to a string.

    ``io`` is the :class:`~url4.io_layer.IOLayer` performing fetches and backend
    calls; it defaults to a batteries-included :class:`~url4.io_http.HttpIOLayer`
    (httpx GET). Pass a :class:`~url4.io_static.StaticIOLayer` for deterministic,
    network-free runs. Pass an explicit ``ctx`` instead to inspect per-run state
    afterwards (e.g. ``ctx.collected_errors``).

    When ``ctx`` is supplied, ``io``/``processor``/``process`` must be left at
    their defaults — the ctx already carries them, and combining both is
    ambiguous (see the ``ValueError`` below). Execution runs on a *child* of the
    supplied ``ctx`` (fresh ``spawn`` wiring, shared scope/io/error-tally/process
    hook), so ``ctx`` itself is never mutated: it is safe to hold on to the same
    ``ExecutionContext`` and pass it to overlapping concurrent ``run()`` calls
    (each gets its own ``spawn`` closure/registry on its own child), and
    ``ctx.collected_errors`` still totals every run's captured row errors
    (they share one error tally by construction).

    ``concurrency`` bounds how many ``ctx.io.fetch`` calls this run (including
    every fragment it spawns) may have in flight at once — the run-wide
    admission-control gate that a bare fan-out group, a fan-out+reduce, and the
    aggregate of a collection's rows would otherwise have no cap on at all
    (per-map ``;iteration.concurrency`` only tightens *within* one map, it does
    not bound the whole run). Defaults to :data:`DEFAULT_RUN_CONCURRENCY`; pass
    ``None`` to opt out and run fully unbounded (the pre-existing behavior),
    e.g. if the ``IOLayer`` already enforces its own limit.

    ``strict_fields`` selects the spec §5.3.4.1 field-path error mode: the
    default (False) is the lenient LLM mode — a missing field / bad index
    substitutes ``""``; True is the strict RDS mode — it raises
    :class:`~url4.errors.ScopeError` with code ``malformed_source``. With a
    supplied ``ctx``, ``strict_fields=True`` tightens the run; the ctx's own
    mode otherwise applies.
    """
    if ctx is not None and (
        io is not None or processor != DEFAULT_PROCESSOR or process is not default_process
    ):
        raise ValueError(
            "run(): pass either `ctx` or `io`/`processor`/`process`, not both — "
            "a supplied `ctx` already carries its own io/processor/process, so "
            "the other kwargs would be silently ignored"
        )
    _validate_concurrency(concurrency)
    run_ctx, owned_io = _run_context(io, ctx, processor, process, strict_fields)
    if concurrency is not None:
        # Wraps only run_ctx's (private, freshly-built-or-childed) io reference,
        # never the caller-supplied ctx.io directly — same non-mutation
        # discipline as the spawn wiring above. Every node in this run, and
        # every fragment it spawns, shares this one bounded wrapper via
        # ExecutionContext.child, so the cap is truly run-wide.
        run_ctx.io = BoundedIOLayer(run_ctx.io, concurrency)
    _wire_spawn(run_ctx, registry)
    try:
        return await Executor(run_ctx).execute(_to_node(target, registry))
    finally:
        if owned_io is not None:
            await owned_io.aclose()


def _run_context(
    io: IOLayer | None,
    ctx: ExecutionContext | None,
    processor: str,
    process: ProcessFn,
    strict_fields: bool,
):
    """The per-run context + the owned adapter to close (None when injected).

    With no ``ctx``, a fresh context is built (defaulting ``io`` to an owned
    HttpIOLayer). A supplied ``ctx`` yields a *child*, never ``ctx`` itself:
    ``_wire_spawn`` mutates whatever it's given, and ctx may be shared across
    overlapping run() calls — mutating it in place would let a second call's
    spawn wiring silently replace the first's, a logical race across the two
    runs' await points. child() shares scope/io/error-tally/process, so
    ``ctx.collected_errors`` still totals correctly. ``strict_fields`` is
    tighten-only on a supplied ctx: a run may opt INTO strictness, never out.
    """
    if ctx is not None:
        run_ctx = ctx.child(ctx.scope)
        if strict_fields:
            run_ctx.strict_fields = True
        return run_ctx, None
    owned_io = None
    if io is None:
        # Composition-root default: imported lazily so the execution core's
        # static import graph never references a concrete transport (httpx).
        from url4.io_http import HttpIOLayer

        io = owned_io = HttpIOLayer()
    run_ctx = ExecutionContext(
        io, processor=processor, process=process, strict_fields=strict_fields
    )
    return run_ctx, owned_io


__all__ = ["Executor", "check_acyclic", "run"]
