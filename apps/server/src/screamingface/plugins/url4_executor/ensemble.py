"""Ensemble interpreter — fan-out N backend calls, then reduce to one response.

Subclass of :class:`Url4Interpreter`. When the expression's source is a
``Url4List`` where **every element** is a ``Url4BackendCall``, the
interpreter enters "ensemble mode":

1. **Fan-out:** dispatch each ``Url4BackendCall`` in parallel via
   ``asyncio.gather``, collecting N string responses.
2. **Reduce:** call a single "reducer" backend (specified by the
   ``processor`` parameter) with the N responses as separate content
   parts in one user message, plus the outer intent as the instruction.
3. **Return:** the reducer's response as JSON (Anthropic Messages shape).

If the expression does NOT match the fan-out shape (e.g. it's a regular
URL list or a single backend call), the ensemble interpreter falls
through to the base :class:`Url4Interpreter` behavior — no change for
existing expressions.

Design decisions (SF-79 ticket, all locked in):

- Q1 = (a): reducer sees only the N responses, NOT the original prompt.
- Q2 = (ii): each response is a separate TextPart in one user message.
- Q3 = (b): unlabeled — no source backend names attached.
- Q4 = (iii): processor is a backend path (``/claude``, ``/claude/synthesizer``).
- Q6 = (a): abort on any fan-out failure — propagate HTTP error.
- Q7 = (a): reducer tool_calls pass through to the caller.
- Q9 = JSON response: ensemble mode returns JSONResponse with the full
  Anthropic Messages shape (via the adapter's from_provider_response).
- Q10 = structured replay: the /data/<key> blob is parsed into
  CoreMessage[] via the adapter layer, not sent as flat text.

Precompilation note: ``$prompt`` and ``$reducer`` are frontend-only
reserved variables. By the time this interpreter sees the expression,
they have been replaced with concrete paths (``/data/<key>`` and
``/claude``). The executor never sees ``$`` variables.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, TypeGuard

from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
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
    """Url4 interpreter with fan-out-reduce semantics.

    Args:
        app: FastAPI app (for plugin lookup and in-process ASGI).
        processor: Backend path for the reducer step (e.g. ``"/claude"``
            or ``"/claude/synthesizer"``). Overrides the default.
    """

    def __init__(self, app: Any = None, *, processor: str | None = None) -> None:
        super().__init__(app)
        self._processor = processor or DEFAULT_PROCESSOR

    async def process(self, sources: str, intent: str | None) -> str:
        """Fallback for non-ensemble expressions. Delegates to base class."""
        return await super().process(sources, intent)

    async def evaluate(self, expr: str) -> str:
        """Full evaluation pipeline with ensemble detection.

        Overrides :meth:`Url4Interpreter.evaluate` to intercept the
        fan-out-reduce shape BEFORE ``resolve()`` flattens the results
        to a single concatenated string.
        """
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
        from screamingface.plugins.url4_executor.decoder import split_intent
        from screamingface.plugins.url4_executor.url4 import parse, resolve_str

        with traced("url4.evaluate"):
            set_span_attrs({"url4.expression": expr[:500]})

            source_expr, raw_intent, broadcast = split_intent(expr.strip())
            set_span_attrs(
                {
                    "url4.has_intent": raw_intent is not None,
                    "url4.broadcast": broadcast,
                }
            )

            # SF-91: Check for collection iteration pattern before parsing.
            # source*(body) detected by finding '*(' at depth 0.
            collection_source, iteration_body = _split_collection_iteration(source_expr)
            if collection_source is not None and iteration_body is not None:
                set_span_attrs({"url4.collection_iteration": True})
                return await self._collection_iterate(
                    collection_source, iteration_body, raw_intent or ""
                )

            source_node = parse(source_expr) if source_expr else None

            # SF-93: intent broadcasting — apply intent per-source
            if broadcast and raw_intent and source_node is not None:
                set_span_attrs({"url4.ensemble": False, "url4.broadcast_mode": True})
                return await self._broadcast_evaluate(source_node, raw_intent)

            if source_node is not None and self._is_fanout(source_node) and raw_intent:
                set_span_attrs({"url4.ensemble": True})
                return await self._ensemble_evaluate(source_node, raw_intent)

            # Not ensemble and not broadcast — fall through to base behavior.
            set_span_attrs({"url4.ensemble": False})

            with traced("url4.resolve_sources"):
                sources = await resolve_str(source_expr, self.app) if source_expr else ""
                src_preview = sources[:4000]
                if len(sources) > 4000:
                    src_preview += f"\n... ({len(sources) - 4000} more chars)"
                set_span_attrs(
                    {
                        "url4.sources_length": len(sources),
                        "url4.response_body": src_preview,
                    }
                )

            from screamingface.plugins.url4_executor.interpreter import resolve_intent

            with traced("url4.resolve_intent"):
                intent = await resolve_intent(raw_intent, self.app) if raw_intent else None
                set_span_attrs(
                    {
                        "url4.intent_length": len(intent) if intent else 0,
                        "url4.response_body": intent[:4000] if intent else "",
                    }
                )

            result = await self.process(sources, intent)
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

    # ------------------------------------------------------------------
    # SF-91: Collection iteration — source*(body)!intent
    # ------------------------------------------------------------------

    async def _collection_iterate(
        self, collection_source: str, iteration_body: str, intent: str
    ) -> str:
        """Iterate over a collection, applying the body expression to each item.

        1. Resolve the collection source (fetch URL/blob).
        2. Parse the body as a collection (JSON array, JSONL, CSV).
        3. For each item, substitute ``$item`` and ``$item.field`` in the
           body expression AND the intent.
        4. Evaluate the substituted expression for each item (which may
           trigger ensemble fan-out-reduce internally).
        5. Collect all results into a newline-joined output.
        """
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
        from screamingface.plugins.url4_executor.collection_parser import parse_collection
        from screamingface.plugins.url4_executor.url4 import resolve_str

        with traced("url4.collection_iterate"):
            # 1. Resolve collection source
            collection_body = await resolve_str(collection_source, self.app)
            items = parse_collection(collection_body)

            set_span_attrs({"url4.collection.item_count": len(items)})

            if not items:
                return ""

            # 2. For each item, substitute $item and evaluate
            async def _process_one(item_json: str) -> str:
                # Substitute $item references in the body expression
                substituted_body = _substitute_item(iteration_body, item_json)
                # Build the full expression: (substituted_body)!intent
                if intent:
                    full_expr = f"({substituted_body})!{intent}"
                else:
                    full_expr = f"({substituted_body})"
                # Recursively evaluate — this may trigger ensemble fan-out
                return await self.evaluate(full_expr)

            results = list(await asyncio.gather(*[_process_one(item) for item in items]))

            set_span_attrs({"url4.collection.result_count": len(results)})
            return "\n".join(results)

    # ------------------------------------------------------------------
    # SF-93: Intent broadcasting — !* operator
    # ------------------------------------------------------------------

    async def _broadcast_evaluate(self, source_node: Url4Node, raw_intent: str) -> str:
        """Apply the intent independently to each source, collect results.

        ``(a, b, c)!*'intent'`` → resolve each source, apply intent to
        each one separately, return newline-joined results.

        For a ``Url4List``, each item is resolved independently and the
        intent is applied via the base interpreter's ``process(sources, intent)``.
        For a non-list source, this is equivalent to a normal ``!`` (one
        application).
        """
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
        from screamingface.plugins.url4_executor.interpreter import resolve_intent

        with traced("url4.broadcast"):
            # Resolve the intent (could be a literal, relurl, etc.)
            intent_text = await resolve_intent(raw_intent, self.app) if raw_intent else ""

            # Get the list of source nodes
            if isinstance(source_node, Url4List):
                items = list(source_node.items)
            else:
                items = [source_node]

            set_span_attrs(
                {
                    "url4.broadcast.item_count": len(items),
                    "url4.broadcast.intent_length": len(intent_text),
                }
            )

            # Resolve each source and apply intent independently
            async def _apply_one(item: Url4Node) -> str:
                source_text = await resolve(item, self.app)
                return await self.process(source_text, intent_text)

            results = list(await asyncio.gather(*[_apply_one(item) for item in items]))

            combined = "\n".join(results)
            set_span_attrs({"url4.broadcast.result_count": len(results)})
            return combined

    # ------------------------------------------------------------------
    # Ensemble internals
    # ------------------------------------------------------------------

    @staticmethod
    def _is_fanout(node: Url4Node) -> TypeGuard[Url4List]:
        """Return True if *node* is a Url4List where every item is a
        Url4BackendCall."""
        if not isinstance(node, Url4List):
            return False
        if not node.items:
            return False
        return all(isinstance(item, Url4BackendCall) for item in node.items)

    async def _ensemble_evaluate(self, source_node: Url4List, raw_intent: str) -> str:
        """Run the fan-out-reduce pipeline.

        1. Resolve the outer intent (the reducer instruction).
        2. Dispatch each Url4BackendCall in parallel.
        3. On any failure, abort with the error (Q6=a).
        4. Build the reducer input as separate content parts (Q2=ii, Q3=b).
        5. Call the reducer backend via the processor path.
        6. Return the reducer's response as JSON string.
        """
        from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
        from screamingface.plugins.url4_executor.interpreter import resolve_intent

        # Resolve the outer intent (could be a literal, /data/<key>, or URL).
        with traced("url4.ensemble.resolve_intent"):
            reducer_instruction = await resolve_intent(raw_intent, self.app) if raw_intent else ""
            set_span_attrs({"url4.ensemble.reducer_instruction_length": len(reducer_instruction)})

        # --- Stage 1: Fan-out ---
        with traced("url4.ensemble.fanout"):
            items = source_node.items
            set_span_attrs({"url4.ensemble.fanout_count": len(items)})

            # Dispatch all in parallel. Q6=(a): any failure aborts the
            # whole ensemble — we do NOT catch exceptions per-element.
            # asyncio.gather with return_exceptions=False (default) will
            # cancel remaining tasks and raise the first exception.
            responses: list[str] = list(
                await asyncio.gather(*[resolve(item, self.app) for item in items])
            )

            set_span_attrs({"url4.ensemble.response_count": len(responses)})

        # --- Stage 2: Reduce ---
        with traced("url4.ensemble.reduce"):
            set_span_attrs({"url4.ensemble.processor": self._processor})

            # Build the reducer input. Pair each response with its AST
            # node so the builder can extract name/weight metadata (SF-88).
            response_entries = [
                _ResponseEntry(
                    text=resp,
                    name=item.name if isinstance(item, Url4BackendCall) else None,
                    weight=item.weight if isinstance(item, Url4BackendCall) else None,
                )
                for item, resp in zip(items, responses, strict=True)
            ]

            # SF-90: substitute $name variable references in the reducer
            # instruction with the actual response text from named fan-out
            # elements. This is executor-level substitution, NOT frontend
            # precompilation ($prompt/$reducer are precompiled; $claude etc
            # are bound at executor time after fan-out completes).
            reducer_instruction = _substitute_response_vars(reducer_instruction, response_entries)

            reducer_input = _build_reducer_input(response_entries, reducer_instruction)

            set_span_attrs({"url4.ensemble.reducer_input_length": len(reducer_input)})

            # Dispatch the reducer through the same backend_call path.
            from screamingface.plugins.url4_executor.url4 import (
                Url4Text,
                _dispatch_backend_call,
            )

            reducer_node = Url4BackendCall(
                path=self._processor,
                intent=Url4Text(value=reducer_input),
            )
            result = await _dispatch_backend_call(reducer_node, self.app)

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


@dataclass
class _ResponseEntry:
    """A fan-out response paired with its source metadata."""

    text: str
    name: str | None = None
    weight: float | None = None


def _build_reducer_input(responses: list[_ResponseEntry], instruction: str) -> str:
    """Format the N fan-out responses + the reducer instruction.

    Q2 = (ii): each response as a separate section.
    Q3 = (b): unlabeled by default — BUT when names and/or weights are
    present (SF-88), they are included so the reducer can reference
    individual responses by name and weight them proportionally.

    Without names/weights::

        [Response 1]
        Two plus two equals four.

        [Response 2]
        4

        [Instruction]
        Synthesize these.

    With names/weights (Kevin's weighted consensus form)::

        claude (weight=40):
        Two plus two equals four.

        codex (weight=30):
        4

        gemini (weight=30):
        The answer is 4.

        [Instruction]
        Merge $claude, $codex, and $gemini into a single, weighted answer.
    """
    has_labels = any(r.name is not None for r in responses)
    parts: list[str] = []

    for i, entry in enumerate(responses, 1):
        if has_labels and entry.name:
            if entry.weight is not None:
                header = f"{entry.name} (weight={entry.weight:g}):"
            else:
                header = f"{entry.name}:"
        else:
            header = f"[Response {i}]"

        parts.append(header)
        parts.append(entry.text.strip())
        parts.append("")  # blank line separator

    parts.append("[Instruction]")
    parts.append(instruction)

    return "\n".join(parts)


def _substitute_response_vars(instruction: str, entries: list[_ResponseEntry]) -> str:
    """Replace ``$name`` tokens in the instruction with actual response text.

    SF-90: executor-level variable substitution. After the fan-out stage
    produces N named responses, any ``$name`` reference in the reducer
    instruction is replaced with the corresponding response text.

    Only entries with a non-None ``name`` participate. Unnamed entries
    are skipped. Unknown ``$name`` references (no matching entry) are
    left as-is so the LLM sees them as literal text.

    This is distinct from frontend precompilation (``$prompt``, ``$reducer``)
    which happens before the executor. Here we're binding runtime results.

    Example::

        entries = [
            _ResponseEntry(text="Four", name="claude"),
            _ResponseEntry(text="4", name="codex"),
        ]
        instruction = "Combine $claude and $codex into one answer"
        → "Combine Four and 4 into one answer"
    """
    if not instruction:
        return instruction

    for entry in entries:
        if entry.name is not None:
            var = f"${entry.name}"
            if var in instruction:
                instruction = instruction.replace(var, entry.text.strip())

    return instruction


def _split_collection_iteration(source_expr: str) -> tuple[str | None, str | None]:
    """Detect the ``source*(body)`` collection iteration pattern.

    Scans for ``*(`` at depth 0 in the source expression. If found,
    splits into (collection_source, iteration_body) where the body
    includes the parenthesized content (without the outer parens).

    Returns ``(None, None)`` if the pattern is not found.

    Examples::

        _split_collection_iteration("/data/abc*(claude:/claude($item.q)!Answer)")
            → ("/data/abc", "claude:/claude($item.q)!Answer")

        _split_collection_iteration("(hello, world)")
            → (None, None)   # no *( pattern
    """
    depth = 0
    for i, ch in enumerate(source_expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "*" and depth == 0:
            # Check if followed by (
            if i + 1 < len(source_expr) and source_expr[i + 1] == "(":
                collection_source = source_expr[:i].strip()
                # Extract body between the *( and the matching )
                body_start = i + 2  # skip *(
                # Find the matching closing paren
                body_depth = 1
                j = body_start
                while j < len(source_expr) and body_depth > 0:
                    if source_expr[j] == "(":
                        body_depth += 1
                    elif source_expr[j] == ")":
                        body_depth -= 1
                    j += 1
                if body_depth == 0:
                    body = source_expr[body_start : j - 1]  # exclude closing )
                    return collection_source, body
    return None, None


def _substitute_item(template: str, item_json: str) -> str:
    """Replace ``$item`` and ``$item.field`` in *template* with values
    from *item_json*.

    - ``$item`` alone is replaced with the full item string.
    - ``$item.field`` is replaced with the field value from the parsed
      JSON object. If the item isn't a JSON object or the field doesn't
      exist, ``$item.field`` is left as-is.
    """
    import json as _json
    import re

    # First handle $item.field references (more specific, must come first)
    field_pattern = re.compile(r"\$item\.([a-zA-Z_][a-zA-Z0-9_]*)")
    parsed_item = None

    def _field_replacer(match: re.Match) -> str:
        nonlocal parsed_item
        if parsed_item is None:
            try:
                parsed_item = _json.loads(item_json)
            except (_json.JSONDecodeError, TypeError):
                parsed_item = {}
        field = match.group(1)
        if isinstance(parsed_item, dict) and field in parsed_item:
            val = parsed_item[field]
            return val if isinstance(val, str) else _json.dumps(val)
        return match.group(0)  # leave as-is if field not found

    result = field_pattern.sub(_field_replacer, template)

    # Then handle bare $item (NOT followed by a dot+fieldname).
    # Use a regex so "$item.field" (where field wasn't found) doesn't
    # get its "$item" portion replaced by the bare handler.
    bare_pattern = re.compile(r"\$item(?!\.[a-zA-Z_])")
    result = bare_pattern.sub(item_json, result)

    return result
