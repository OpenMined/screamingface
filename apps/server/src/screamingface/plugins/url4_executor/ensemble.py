"""Ensemble interpreter — fan-out N backend calls, then reduce to one response.

Subclass of :class:`Url4Interpreter`. Four evaluation paths live here,
dispatched from :meth:`EnsembleInterpreter.evaluate`:

1. **Collection iteration** (``source*(body)!intent``) — parse the
   collection, expand ``$item`` per row, evaluate in parallel.
2. **Broadcast** (``(a, b, c)!*intent``) — apply the same intent to
   each source independently.
3. **Fan-out + reduce** (``(call1, call2, call3)!reduce-instruction``) —
   dispatch N ``Url4BackendCall``s in parallel, feed all responses to
   a single reducer call.
4. **Single source** — the default: delegate to the base interpreter's
   ``process(sources, intent)``.

Design decisions (SF-79 ticket, all locked in):

- Q1 = (a): reducer sees only the N responses, NOT the original prompt.
- Q2 = (ii): each response is a separate TextPart in one user message.
- Q3 = (b): unlabeled — no source backend names attached (unless
  explicitly provided in SF-88 named-source syntax).
- Q4 = (iii): processor is a backend path (``/claude``, ``/claude/synthesizer``).
- Q6 = (a): abort on any fan-out failure — propagate HTTP error.
- Q7 = (a): reducer tool_calls pass through to the caller.

Precompilation note: ``$prompt`` and ``$reducer`` are frontend-only
reserved variables. By the time this interpreter sees the expression,
they have been replaced with concrete paths. The executor never sees
``$`` variables at the frontend level (``$item``, ``$item.field``, and
``$<name>`` response references ARE executor-level substitutions and
live in :mod:`ensemble_helpers`).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, TypeGuard

if TYPE_CHECKING:
    from screamingface.plugins.url4_executor.decoder import ForeachDirectives

from screamingface.plugins.url4_executor.ensemble_helpers import (
    FanoutResponse,
    _build_reducer_input,  # noqa: F401 — legacy re-export
    _ResponseEntry,  # noqa: F401 — legacy re-export
    _split_collection_iteration,  # noqa: F401 — legacy re-export
    _substitute_item,  # noqa: F401 — legacy re-export
    _substitute_response_vars,  # noqa: F401 — legacy re-export
    build_reducer_input,
    split_collection_iteration,
    substitute_item,
    substitute_response_vars,
)
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4List,
    Url4Node,
    resolve,
)

logger = logging.getLogger(__name__)

# Default reducer backend path when ?processor= is not specified.
DEFAULT_PROCESSOR = "/claude"


class EnsembleInterpreter(Url4Interpreter):
    """URL4 interpreter with fan-out-reduce + collection iteration + broadcast.

    Args:
        app: FastAPI app (for plugin lookup and in-process ASGI).
        processor: Backend path for the reducer step (e.g. ``"/claude"``
            or ``"/claude/synthesizer"``). Overrides the default.
    """

    def __init__(self, app: Any = None, *, processor: str | None = None) -> None:
        super().__init__(app)
        self._processor = processor or DEFAULT_PROCESSOR

    async def process(self, sources: str, intent: str | None, env: Env | None = None) -> str:
        """Fallback for non-ensemble expressions. Delegates to base class."""
        return await super().process(sources, intent, env)

    # ------------------------------------------------------------------
    # Dispatcher — picks the right evaluation strategy for the expression
    # ------------------------------------------------------------------

    async def evaluate(self, expr: str, env: Env | None = None) -> str:
        """Choose one of four evaluation strategies and run it.

        The dispatcher owns only the decision tree. Each strategy (the
        ``_*_evaluate`` methods below) owns its own evaluation pipeline
        + tracing. Order matters: collection iteration must come before
        fan-out detection because ``source*(…)`` is a distinct shape.
        """
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
        from screamingface.plugins.url4_executor.decoder import split_intent
        from screamingface.plugins.url4_executor.url4 import parse

        with traced("url4.evaluate"):
            if env is None:
                env = Env.root()
            set_span_attrs({"url4.expression": expr[:500]})
            source_expr, raw_intent, broadcast = split_intent(expr.strip())
            set_span_attrs(
                {
                    "url4.has_intent": raw_intent is not None,
                    "url4.broadcast": broadcast,
                }
            )

            from screamingface.plugins.url4_executor.decoder import split_foreach_annotations

            source_expr, directives = split_foreach_annotations(source_expr)

            # 1. Collection iteration (``source*(body)``) — matched by
            #    scanning for ``*(`` at depth 0.
            collection_source, iteration_body = split_collection_iteration(source_expr)
            if collection_source is not None and iteration_body is not None:
                set_span_attrs({"url4.collection_iteration": True})
                return await self._collection_iterate(
                    collection_source, iteration_body, raw_intent or "", env, directives
                )

            source_node = parse(source_expr) if source_expr else None

            # 2. Broadcast (``!*`` operator) — apply intent per-source.
            if broadcast and raw_intent and source_node is not None:
                set_span_attrs({"url4.ensemble": False, "url4.broadcast_mode": True})
                return await self._broadcast_evaluate(source_node, raw_intent, env)

            # 3. Fan-out + reduce — source is a list of backend calls.
            if source_node is not None and self._is_fanout(source_node) and raw_intent:
                set_span_attrs({"url4.ensemble": True})
                return await self._ensemble_evaluate(source_node, raw_intent, env)

            # 4. Default single-source path.
            set_span_attrs({"url4.ensemble": False})
            return await self._single_source_evaluate(source_expr, raw_intent, env)

    # ------------------------------------------------------------------
    # Strategy 1: collection iteration (SF-91)
    # ------------------------------------------------------------------

    async def _collection_iterate(
        self,
        collection_source: str,
        iteration_body: str,
        intent: str,
        env: Env | None = None,
        directives: ForeachDirectives | None = None,
    ) -> str:
        """Iterate over a collection, applying the body expression to each item.

        1. Resolve the collection source (fetch URL/blob).
        2. Parse the body as a collection (JSON array, JSONL, CSV).
        3. For each item, substitute ``$item`` and ``$item.field`` in
           the body and the intent.
        4. Evaluate the substituted expression per item (may recurse
           into ensemble fan-out-reduce).
        5. Newline-join all results.

        If ``directives.concurrency`` is set, a semaphore caps the number
        of items evaluated in parallel. If ``directives.on_error == "collect"``,
        per-item exceptions are captured as ``{"error": ...}`` JSON elements
        instead of aborting the whole iteration.
        """
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
        from screamingface.plugins.url4_executor.collection_parser import parse_collection
        from screamingface.plugins.url4_executor.decoder import ForeachDirectives
        from screamingface.plugins.url4_executor.url4 import resolve_str

        with traced("url4.collection_iterate"):
            collection_body = await resolve_str(collection_source, self.app, env)
            items = parse_collection(collection_body)
            set_span_attrs({"url4.collection.item_count": len(items)})

            if not items:
                return ""

            directives = directives or ForeachDirectives()

            async def _process_one(item_json: str) -> str:
                substituted_body = substitute_item(iteration_body, item_json)
                full_expr = f"({substituted_body})!{intent}" if intent else f"({substituted_body})"
                return await self.evaluate(full_expr, env)

            sem = asyncio.Semaphore(directives.concurrency) if directives.concurrency else None

            async def _guarded(item_json: str) -> str:
                if sem is None:
                    return await _process_one(item_json)
                async with sem:
                    return await _process_one(item_json)

            if directives.on_error == "collect":
                raw = await asyncio.gather(*[_guarded(i) for i in items], return_exceptions=True)
                results = [
                    r
                    if not isinstance(r, BaseException)
                    else json.dumps({"error": {"kind": type(r).__name__, "message": str(r)}})
                    for r in raw
                ]
            else:
                results = list(await asyncio.gather(*[_guarded(i) for i in items]))
            set_span_attrs({"url4.collection.result_count": len(results)})
            return "\n".join(results)

    # ------------------------------------------------------------------
    # Strategy 2: intent broadcasting (SF-93, ``!*``)
    # ------------------------------------------------------------------

    async def _broadcast_evaluate(
        self, source_node: Url4Node, raw_intent: str, env: Env | None = None
    ) -> str:
        """Apply the intent independently to each source, collect results.

        ``(a, b, c)!*'intent'`` → resolve each source, apply the intent
        to each one separately, return newline-joined results.
        """
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
        from screamingface.plugins.url4_executor.interpreter import resolve_intent

        with traced("url4.broadcast"):
            intent_text = await resolve_intent(raw_intent, self.app, env) if raw_intent else ""

            items = list(source_node.items) if isinstance(source_node, Url4List) else [source_node]
            set_span_attrs(
                {
                    "url4.broadcast.item_count": len(items),
                    "url4.broadcast.intent_length": len(intent_text),
                }
            )

            async def _apply_one(item: Url4Node) -> str:
                source_text = await resolve(item, self.app, env)
                return await self.process(source_text, intent_text, env)

            results = list(await asyncio.gather(*[_apply_one(item) for item in items]))
            set_span_attrs({"url4.broadcast.result_count": len(results)})
            return "\n".join(results)

    # ------------------------------------------------------------------
    # Strategy 3: fan-out + reduce
    # ------------------------------------------------------------------

    @staticmethod
    def _is_fanout(node: Url4Node) -> TypeGuard[Url4List]:
        """True if ``node`` is a ``Url4List`` of ``Url4BackendCall``s."""
        if not isinstance(node, Url4List):
            return False
        if not node.items:
            return False
        return all(isinstance(item, Url4BackendCall) for item in node.items)

    async def _ensemble_evaluate(
        self, source_node: Url4List, raw_intent: str, env: Env | None = None
    ) -> str:
        """Fan-out N backend calls, reduce via the configured processor.

        1. Resolve the outer intent (reducer instruction).
        2. Dispatch each ``Url4BackendCall`` in parallel.
        3. On any failure, abort with the error (Q6=a).
        4. Build the reducer input as separate sections (Q2=ii, Q3=b).
        5. Call the reducer backend via the processor path.
        6. Return the reducer's response.
        """
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
        from screamingface.plugins.url4_executor.interpreter import resolve_intent
        from screamingface.plugins.url4_executor.url4 import Url4Text
        from screamingface.plugins.url4_executor.url4_resolve import _dispatch_backend_call

        with traced("url4.ensemble.resolve_intent"):
            reducer_instruction = (
                await resolve_intent(raw_intent, self.app, env) if raw_intent else ""
            )
            set_span_attrs({"url4.ensemble.reducer_instruction_length": len(reducer_instruction)})

        with traced("url4.ensemble.fanout"):
            items = source_node.items
            set_span_attrs({"url4.ensemble.fanout_count": len(items)})
            # asyncio.gather with return_exceptions=False (default) cancels
            # remaining tasks and raises the first exception (Q6=a).
            responses: list[str] = list(
                await asyncio.gather(*[resolve(item, self.app, env) for item in items])
            )
            set_span_attrs({"url4.ensemble.response_count": len(responses)})

        with traced("url4.ensemble.reduce"):
            set_span_attrs({"url4.ensemble.processor": self._processor})

            response_entries = [
                FanoutResponse(
                    text=resp,
                    name=item.name if isinstance(item, Url4BackendCall) else None,
                    weight=item.weight if isinstance(item, Url4BackendCall) else None,
                )
                for item, resp in zip(items, responses, strict=True)
            ]

            reducer_instruction = substitute_response_vars(reducer_instruction, response_entries)
            reducer_input = build_reducer_input(response_entries, reducer_instruction)
            set_span_attrs({"url4.ensemble.reducer_input_length": len(reducer_input)})

            reducer_node = Url4BackendCall(
                path=self._processor,
                intent=Url4Text(value=reducer_input),
            )
            result = await _dispatch_backend_call(reducer_node, self.app, env)

            result_preview = result[:4000]
            if len(result) > 4000:
                result_preview += f"\n... ({len(result) - 4000} more chars)"
            set_span_attrs(
                {
                    "url4.ensemble.result_length": len(result),
                    "url4.ensemble.response_body": result_preview,
                }
            )
            return result

    # ------------------------------------------------------------------
    # Strategy 4: single source (default / base interpreter behavior)
    # ------------------------------------------------------------------

    async def _single_source_evaluate(
        self, source_expr: str, raw_intent: str | None, env: Env | None = None
    ) -> str:
        """Resolve sources and apply intent via the base interpreter.

        Mirrors :meth:`Url4Interpreter.evaluate` with the same tracing
        spans — duplicated here so the dispatcher can short-circuit
        before parsing when an earlier strategy matches.
        """
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
        from screamingface.plugins.url4_executor.interpreter import resolve_intent
        from screamingface.plugins.url4_executor.url4 import resolve_str

        with traced("url4.resolve_sources"):
            sources = await resolve_str(source_expr, self.app, env) if source_expr else ""
            src_preview = sources[:4000]
            if len(sources) > 4000:
                src_preview += f"\n... ({len(sources) - 4000} more chars)"
            set_span_attrs(
                {
                    "url4.sources_length": len(sources),
                    "url4.response_body": src_preview,
                }
            )

        with traced("url4.resolve_intent"):
            intent = await resolve_intent(raw_intent, self.app, env) if raw_intent else None
            set_span_attrs(
                {
                    "url4.intent_length": len(intent) if intent else 0,
                    "url4.response_body": intent[:4000] if intent else "",
                }
            )

        result = await self.process(sources, intent, env)
        result_preview = result[:4000]
        if len(result) > 4000:
            result_preview += f"\n... ({len(result) - 4000} more chars)"
        set_span_attrs(
            {
                "url4.result_length": len(result),
                "url4.response_body": result_preview,
            }
        )
        return result
