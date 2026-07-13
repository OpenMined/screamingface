"""The requestor facade — :class:`Client` and the :class:`Url4Result` envelope.

One execution path serves local and remote queries alike: helper methods build
an AST via :mod:`url4.builders`, a node target (when set) wraps it into a
:class:`~url4.nodes.RemoteExpr` — so the wire hop is just another DAG node —
the tree renders to canonical text, and :func:`url4.dag.run` executes it. The
rendered string is returned as :attr:`Url4Result.request`: the loggable,
shareable, re-runnable audit artifact the protocol is built around (spec §1.2).

Remote encodings (all reparse-verified by the renderer):
- ``query``     → ``(url4://node/path(ctx)!intent)`` — the parenthesized form
  keeps the intent executing on the remote node (bare, the top-level ``!``
  split would hoist it to a local intent).
- ``broadcast`` → the ``broadcast`` flag rides as a protocol param before
  ``q=``; the remote envelope decode folds it back into ``!*`` (§6.1.1).
- ``iterate(reduce=…)`` → the canonical reduce-over-iteration text
  ``q=(coll*(body)!'per row')!reducer`` (§5.3).

Known grammar limit: multi-valued params (``triggers=1,2``) cannot ride a
*nested* remote expression — a depth-0 comma would split the enclosing source
list — so they raise :class:`~url4.errors.RenderError` on remote queries;
local (top-level) queries carry them fine.

Deliberately absent: a module-level ``query()`` — a global async client binds
an httpx pool to one event loop, a footgun in notebooks and servers. Construct
a :class:`Client` (ideally ``async with``) and own its lifecycle.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from url4.builders import ParamsLike, SourceLike, _pairs, _rewrite_reducer_iteration
from url4.builders import broadcast as _broadcast
from url4.builders import expr as _expr
from url4.builders import iterate as _iterate
from url4.builders import reduce as _reduce
from url4.context import Context
from url4.dag import DEFAULT_PROCESSOR, DEFAULT_RUN_CONCURRENCY, ExecutionContext, run
from url4.dag.node import ProcessFn, default_process
from url4.io_layer import IOLayer
from url4.nodes import Expression, Iteration, Node, Params, RemoteExpr
from url4.render import _render_source, render


@dataclass(frozen=True)
class Url4Result:
    """A url4 evaluation outcome: the result body plus its request provenance.

    ``request`` is the exact canonical expression that ran — log it, share it,
    re-run it. Structured accessors decode the body on demand; the envelope
    fields of spec Part C (per-source attribution, budgets) land here once the
    executor reports them.
    """

    text: str
    request: str

    def __str__(self) -> str:
        return self.text

    @property
    def data(self) -> Any:
        """The body decoded as JSON; raises ``ValueError`` for non-JSON bodies."""
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"result body is not JSON (request {self.request!r}): {self.text[:80]!r}"
            ) from exc

    @property
    def elements(self) -> list[Any]:
        """Per-element results of an iteration/broadcast (a JSON array body)."""
        data = self.data
        if not isinstance(data, list):
            raise ValueError(
                f"result of {self.request!r} is not a JSON list (got {type(data).__name__}) — "
                "elements apply to iteration and broadcast results (spec §5.3.8, §6.1.4)"
            )
        return data


class Client:
    """The requestor-side entry point for evaluating url4 expressions.

    ``io`` is the outbound :class:`~url4.io_layer.IOLayer`; omitted, an
    httpx-backed adapter is created lazily and owned (closed by
    :meth:`aclose` / ``async with``). ``node`` sets a default remote target
    (``"url4://host/path"`` / ``"host"``); without one, expressions evaluate
    locally against ``io``. ``processor`` is the endpoint local intent
    execution dispatches to (spec: the node's intent processor).
    """

    def __init__(
        self,
        io: IOLayer | None = None,
        *,
        node: str | None = None,
        path: str = "/v1",
        processor: str = DEFAULT_PROCESSOR,
        process: ProcessFn = default_process,
        concurrency: int | None = DEFAULT_RUN_CONCURRENCY,
        strict_fields: bool = False,
    ) -> None:
        self._io = io
        self._owned_io: IOLayer | None = None
        self._node = node
        self._path = path
        self._processor = processor
        self._process = process
        self._concurrency = concurrency
        self._strict_fields = strict_fields

    # --- lifecycle -----------------------------------------------------------

    async def aclose(self) -> None:
        """Close the lazily-owned io adapter, if any (injected io is left alone)."""
        owned = self._owned_io
        self._owned_io = None
        if owned is not None:
            await owned.aclose()  # type: ignore[attr-defined]  # owned is always HttpIOLayer

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    def _effective_io(self) -> IOLayer:
        if self._io is not None:
            return self._io
        if self._owned_io is None:
            from url4.io_http import HttpIOLayer  # composition root: lazy transport import

            self._owned_io = HttpIOLayer()
        return self._owned_io

    # --- the query surface ------------------------------------------------------

    async def query(
        self,
        *sources: SourceLike,
        intent: str | Node | None = None,
        node: str | None = None,
        path: str | None = None,
        quorum: int | None = None,
        triggers: tuple[int, ...] | list[int] | None = None,
        t: float | int | None = None,
        fmt: str | None = None,
        params: ParamsLike = (),
    ) -> Url4Result:
        """``(sources)!intent`` — the core request; everything else is sugar."""
        proto = _proto_params(quorum, triggers, t, fmt, params)
        return await self.execute(
            _expr(*sources, intent=intent), node=node, path=path, params=proto
        )

    async def broadcast(
        self,
        *sources: SourceLike,
        intent: str | Node,
        node: str | None = None,
        path: str | None = None,
        params: ParamsLike = (),
    ) -> Url4Result:
        """``(sources)!*intent`` — apply the intent per source (§6.1)."""
        return await self.execute(
            _broadcast(*sources, intent=intent), node=node, path=path, params=_pairs(params)
        )

    async def iterate(
        self,
        collection: SourceLike | list[SourceLike] | tuple[SourceLike, ...],
        body: str | Node | list[SourceLike] | tuple[SourceLike, ...] = "",
        *,
        intent: str | Node | None = None,
        reduce: str | Node | None = None,
        node: str | None = None,
        path: str | None = None,
        concurrency: int | None = None,
        on_error: str | None = None,
        slice: tuple[int, int] | None = None,
        fmt_result: str | None = None,
    ) -> Url4Result:
        """``collection*(body)!intent`` — evaluate per element (§5.3)."""
        root = _iterate(
            collection,
            body,
            intent=intent,
            reduce=reduce,
            concurrency=concurrency,
            on_error=on_error,
            slice=slice,
            fmt_result=fmt_result,
        )
        return await self.execute(root, node=node, path=path)

    async def reduce(
        self,
        calls: list[SourceLike] | tuple[SourceLike, ...],
        instruction: str | Node,
        *,
        node: str | None = None,
        path: str | None = None,
        params: ParamsLike = (),
    ) -> Url4Result:
        """``(call1, call2, …)!instruction`` — fan-out/reduce sugar (§2)."""
        return await self.execute(
            _reduce(calls, instruction), node=node, path=path, params=_pairs(params)
        )

    async def execute(
        self,
        root: Expression | Iteration,
        *,
        node: str | None = None,
        path: str | None = None,
        params: Params = (),
    ) -> Url4Result:
        """Evaluate a prebuilt AST, remotely when a node target applies."""
        target = node or self._node
        if target is None:
            request = render(_with_params(root, params))
        else:
            request = render(_as_remote(root, target, path or self._path, params))
        return await self.evaluate(request)

    async def evaluate(
        self, expression: str | Node, *, env: Mapping[str, object] | None = None
    ) -> Url4Result:
        """Evaluate raw url4 text or an AST as-is (no routing, no param merging).

        ``env`` seeds the lexical scope: ``$name`` references in the expression
        resolve against it (the mockups' ``Env``).
        """
        request = expression if isinstance(expression, str) else render(expression)
        ctx = ExecutionContext(
            self._effective_io(),
            processor=self._processor,
            process=self._process,
            scope=Context(bindings=dict(env)) if env else None,
            strict_fields=self._strict_fields,
        )
        text = await run(request, ctx=ctx, concurrency=self._concurrency)
        return Url4Result(text=text, request=request)


# --- routing helpers -------------------------------------------------------------


def _proto_params(
    quorum: int | None,
    triggers: tuple[int, ...] | list[int] | None,
    t: float | int | None,
    fmt: str | None,
    extra: ParamsLike,
) -> Params:
    named = (
        ("quorum", quorum),
        ("triggers", None if triggers is None else ",".join(str(n) for n in triggers)),
        ("t", t),
        ("fmt", fmt),
    )
    return _pairs([(k, v) for k, v in named if v is not None]) + _pairs(extra)


def _with_params(root: Expression | Iteration, params: Params) -> Expression | Iteration:
    if not params:
        return root
    if isinstance(root, Iteration):
        # The iteration envelope has no params slot: "coll*(b)!i;quorum=2" would
        # silently DROP quorum on decode (IterationEnvelope keeps directives only).
        raise ValueError(
            "protocol params cannot ride a local iteration — the envelope decode "
            "drops them; wrap it in expr(...) or send it to a node"
        )
    return Expression(
        sources=root.sources,
        intent=root.intent,
        broadcast=root.broadcast,
        params=root.params + params,
    )


def _as_remote(
    root: Expression | Iteration, target: str, default_path: str, proto: Params
) -> RemoteExpr:
    """Wrap ``root`` as a remote expression addressed to ``target``.

    The remote node evaluates the full ``q=(context)!intent`` — sources resolve
    THERE (spec §5.6.3 pass-through), the intent dispatches to its processor.
    """
    authority, path = _split_target(target, default_path)
    if isinstance(root, Iteration):
        rewritten = _rewrite_reducer_iteration(root)
        # a reducer iteration becomes its (iteration)!reducer group; a plain
        # one becomes the group's single source
        root = rewritten if isinstance(rewritten, Expression) else _expr(rewritten)
    if root.broadcast:
        # !* has no slot in the canonical q=(ctx)!intent form; the broadcast
        # param is its spec-equivalent and folds back on the remote decode (§6.1.1).
        proto = proto + (("broadcast", None),)
    context = ", ".join(_render_source(s) for s in root.sources)
    return RemoteExpr(
        authority=authority,
        path=path,
        context=context or None,
        intent=root.intent,
        params=root.params + proto,
    )


def _split_target(target: str, default_path: str) -> tuple[str, str]:
    stripped = target.removeprefix("url4://").strip("/") or ""
    authority, sep, path = stripped.partition("/")
    if not authority:
        raise ValueError(f"invalid node target {target!r} — expected 'url4://host[/path]'")
    return authority, f"/{path}" if sep else default_path


__all__ = ["Client", "Url4Result"]
