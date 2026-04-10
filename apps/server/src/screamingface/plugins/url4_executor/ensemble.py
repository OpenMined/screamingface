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
from typing import Any

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

            source_expr, raw_intent = split_intent(expr.strip())
            set_span_attrs({"url4.has_intent": raw_intent is not None})

            source_node = parse(source_expr) if source_expr else None

            if source_node is not None and self._is_fanout(source_node) and raw_intent:
                set_span_attrs({"url4.ensemble": True})
                return await self._ensemble_evaluate(source_node, raw_intent)

            # Not ensemble — fall through to base behavior.
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
    # Ensemble internals
    # ------------------------------------------------------------------

    @staticmethod
    def _is_fanout(node: Url4Node) -> bool:
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
