"""The DAG core contracts: the :class:`DagNode` protocol and :class:`ExecutionContext`.

This module is the DAG's dependency sink — it imports only the language-core
leaves (context, io_layer), so node implementations, the compiler, and the
executor can all depend on it without cycles.

Design notes
------------
- **Expression-problem flip.** The parse tree (:mod:`url4.nodes`) is a closed
  union of pure-data nodes with external operations. DAG nodes invert that:
  behavior lives ON the node (``resolve``), so the node set is *open* — any
  object satisfying :class:`DagNode` executes, which is what custom-node
  extensibility requires (Strategy per node type, Liskov behind the protocol).
- **The executor delivers inputs; nodes never await their own deps.** ``deps``
  declares labeled edges (role → node, insertion-ordered — join and dispatch
  order derive from it); ``resolve`` receives the resolved values by role.
  Scheduling policy (memoization, parallelism, cancellation) lives entirely in
  the executor, and nodes stay pure and unit-testable with a plain dict. The
  one capability a node reaches for is I/O, via ``ctx.io`` (the injected
  :class:`~url4.io_layer.IOLayer` port).
- **Payloads are strings** at every language-level boundary. ``list[str]`` is
  an internal contract between the multi-valued producers
  (:class:`~url4.dag.nodes.MapNode` rows, :class:`~url4.dag.nodes.ExpandNode`
  elements) and their Collect/Process consumer: rows may contain newlines, so
  a joined-string edge would corrupt row boundaries.
  :class:`SourceFailure` is the third payload shape: a *tolerated* terminal
  failure of an ``;optional`` source (spec §10.1) — data, not an exception, so
  it flows through the group gather instead of cancelling the TaskGroup.
  Custom nodes should contract on ``str``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import NoReturn, Protocol, runtime_checkable

from url4.context import Context
from url4.io_layer import (
    FetchRequest,
    FetchResult,
    IOLayer,
    SupportsFetchEx,
    SupportsHoldings,
)

DEFAULT_PROCESSOR = "/claude"


@dataclass(frozen=True)
class SourceFailure:
    """A tolerated source failure: the terminal state of a failed ``;optional``
    source (spec Part A, "Terminal state"). Carries the spec error ``code`` and
    message so the envelope can report the outcome; group nodes skip it in the
    packed sources and in ``$name``/``$N`` population."""

    code: str
    message: str


Payload = str | list[str] | SourceFailure

ProcessFn = Callable[[str, str | None, Context], Awaitable[str]]
SpawnFn = Callable[[str, Context], Awaitable[str]]
ExecuteNodeFn = Callable[["DagNode", Context], Awaitable[Payload]]


@runtime_checkable
class DagNode(Protocol):
    """The executable-node port: labeled dependency edges + one operation."""

    @property
    def deps(self) -> Mapping[str, DagNode]:
        """Labeled edges, role → node. Insertion order is significant."""
        ...

    async def resolve(self, inputs: Mapping[str, Payload], ctx: ExecutionContext) -> Payload:
        """Produce this node's value from its resolved dependency ``inputs``."""
        ...


async def default_process(sources: str, intent: str | None, scope: Context) -> str:
    """The default merge of resolved sources and intent (Template Method hook)."""
    if intent and sources:
        return f"{intent}\n\n{sources}"
    return intent or sources or ""


class _ErrorTally:
    """A shared mutable counter so child contexts report into one total."""

    def __init__(self) -> None:
        self.count = 0


# The default run-wide fan-out cap (see BoundedIOLayer below). Without it, a
# bare fan-out group, a FanoutReduceNode's parallel calls, or the aggregate of
# many MapNode rows each issue unboundedly many concurrent ctx.io.fetch calls,
# with only an IOLayer's own (possibly nonexistent) backstop — httpx's
# connection pool for HttpIOLayer, nothing at all for StaticIOLayer or a custom
# adapter. This is deliberately looser than MapNode's per-iteration default
# (DEFAULT_MAP_CONCURRENCY): it caps the WHOLE run's I/O, of which any one map
# is only a part.
DEFAULT_RUN_CONCURRENCY = 32


class BoundedIOLayer:
    """Wraps an :class:`~url4.io_layer.IOLayer` with a semaphore-bounded ``fetch``.

    This is the run-wide admission-control gate: the semaphore is acquired
    only around the inner ``fetch`` call itself — never across substitution,
    compilation, or a node's own scope-building — so it bounds concurrent I/O
    in flight without serializing anything else. :func:`run` installs one
    instance per run and every node (and every spawned sub-executor, via
    :meth:`ExecutionContext.child` sharing ``io``) fetches through it, so a
    fan-out of N independent sources or M map rows collectively never exceeds
    the bound — layered *underneath* any node-local cap such as MapNode's
    ``;iteration.concurrency``, never replacing it.

    The optional capability ports (``fetch_ex``, ``fetch_holdings``) are
    forwarded — bounded by the same semaphore — but only when the *inner*
    adapter provides them: they are bound as instance attributes so a
    ``runtime_checkable`` isinstance test against the wrapper reports exactly
    the wrapped adapter's capabilities, never more.
    """

    # Conditionally bound in __init__ (annotation only — no class attribute, so
    # hasattr/isinstance stay false when the inner adapter lacks the port).
    fetch_ex: Callable[[FetchRequest], Awaitable[FetchResult]]
    fetch_holdings: Callable[[str | None, str | None], Awaitable[str]]

    def __init__(self, inner: IOLayer, limit: int) -> None:
        self._inner = inner
        self._sem = asyncio.Semaphore(limit)
        if isinstance(inner, SupportsFetchEx):
            self.fetch_ex = self._bounded_fetch_ex
        if isinstance(inner, SupportsHoldings):
            self.fetch_holdings = self._bounded_fetch_holdings

    async def fetch(self, target: str, *, relative: bool) -> str:
        async with self._sem:
            return await self._inner.fetch(target, relative=relative)

    async def _bounded_fetch_ex(self, request: FetchRequest) -> FetchResult:
        async with self._sem:
            return await self._inner.fetch_ex(request)  # type: ignore[attr-defined]

    async def _bounded_fetch_holdings(self, identity: str | None, collection: str | None) -> str:
        async with self._sem:
            return await self._inner.fetch_holdings(identity, collection)  # type: ignore[attr-defined]


class ExecutionContext:
    """Per-run capabilities handed to every ``resolve`` call.

    Carries the :class:`~url4.io_layer.IOLayer` port ``io`` (all I/O flows
    through it), the reducer ``processor`` path, the lexical ``scope`` for
    ``$name`` fallback in dynamically spawned fragments, the overridable
    ``process`` merge hook, ``strict_fields`` (the spec §5.3.4.1 field-path
    error mode: lenient/LLM by default, strict/RDS when True), and two
    executor-injected escape hatches nodes only ever call:

    - ``spawn`` — compile and execute a url4 *text fragment* on a fresh
      executor (MapNode rows, lazy sub-expressions);
    - ``execute_node`` — execute a *prebuilt node subtree* on a fresh executor
      (GuardNode's isolation boundary: a guarded failure must surface as a
      value, which requires the subtree to fail inside its own TaskGroup, not
      the outer one).

    Contexts are per-run — no state is shared across runs — but ``child``
    frames share the run's error tally so ``collected_errors`` totals
    per-row failures captured under ``;iteration.on_error=collect``.
    """

    def __init__(
        self,
        io: IOLayer,
        *,
        processor: str = DEFAULT_PROCESSOR,
        process: ProcessFn = default_process,
        scope: Context | None = None,
        spawn: SpawnFn | None = None,
        strict_fields: bool = False,
        execute_node: ExecuteNodeFn | None = None,
        _tally: _ErrorTally | None = None,
    ) -> None:
        self.io = io
        self.processor = processor
        self.process = process
        self.scope = scope if scope is not None else Context.root()
        self.strict_fields = strict_fields
        self._tally = _tally if _tally is not None else _ErrorTally()
        self.spawn: SpawnFn = spawn if spawn is not None else _spawn_unset
        self.execute_node: ExecuteNodeFn = (
            execute_node if execute_node is not None else _execute_node_unset
        )

    @property
    def collected_errors(self) -> int:
        """Per-row failures captured under ``;iteration.on_error=collect`` this run."""
        return self._tally.count

    def record_collected_error(self) -> None:
        self._tally.count += 1

    def child(self, scope: Context) -> ExecutionContext:
        """A context for a spawned fragment: new scope, shared everything else."""
        return ExecutionContext(
            self.io,
            processor=self.processor,
            process=self.process,
            scope=scope,
            spawn=self.spawn,
            strict_fields=self.strict_fields,
            execute_node=self.execute_node,
            _tally=self._tally,
        )


async def _spawn_unset(text: str, scope: Context) -> str:
    raise RuntimeError(
        "ExecutionContext.spawn is not wired — execute nodes via url4.dag.run/Executor"
    )


async def _execute_node_unset(node: DagNode, scope: Context) -> Payload:
    raise RuntimeError(
        "ExecutionContext.execute_node is not wired — execute nodes via url4.dag.run/Executor"
    )


def first_error(group: BaseExceptionGroup) -> BaseException | None:
    """The first non-cancellation leaf of an exception group, or ``None``.

    TaskGroup failures arrive as (possibly nested) groups; url4 callers catch
    plain :class:`~url4.errors.Url4Error` subclasses, so the executor and
    MapNode unwrap with this before re-raising.
    """
    for exc in group.exceptions:
        if isinstance(exc, BaseExceptionGroup):
            found = first_error(exc)
            if found is not None:
                return found
        elif not isinstance(exc, asyncio.CancelledError):
            return exc
    return None


def reraise_first(group: BaseExceptionGroup) -> NoReturn:
    """Re-raise a TaskGroup failure as the plain error url4 callers expect.

    Unwrap the (possibly nested) group to its first non-cancellation leaf via
    :func:`first_error` and re-raise that with ``from None``; a group carrying
    only cancellations re-raises verbatim. Shared by the top-level executor and
    :class:`~url4.dag.nodes.MapNode` so both surface the identical exception
    type for the same underlying failure.
    """
    error = first_error(group)
    if error is None:
        raise group
    raise error from None


__all__ = [
    "DEFAULT_PROCESSOR",
    "DEFAULT_RUN_CONCURRENCY",
    "BoundedIOLayer",
    "DagNode",
    "ExecuteNodeFn",
    "ExecutionContext",
    "Payload",
    "ProcessFn",
    "SourceFailure",
    "SpawnFn",
    "default_process",
    "first_error",
    "reraise_first",
]
