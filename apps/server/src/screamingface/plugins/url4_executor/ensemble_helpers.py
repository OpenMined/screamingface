"""Helper functions for the ensemble interpreter.

Extracted from :mod:`ensemble` during SF-108 so the interpreter itself
can shrink to a thin dispatch over the four evaluation strategies
(collection iteration, broadcast, ensemble fan-out, single-source).

Public names (unprefixed): ``FanoutResponse``, ``build_reducer_input``,
``substitute_response_vars``, ``substitute_env_vars``,
``split_collection_iteration``, ``substitute_item``. The legacy
underscore-prefixed aliases are kept for back-compat with existing
callers and tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from screamingface.plugins.url4_executor.scope import Env


@dataclass
class FanoutResponse:
    """A fan-out response paired with its source metadata.

    Produced during the ensemble fan-out stage — one entry per
    ``Url4BackendCall`` in the source list. ``name`` and ``weight`` are
    carried through from the backend-call AST node so the reducer can
    reference individual responses by name (``$claude``) or apply a
    weighted-consensus strategy.
    """

    text: str
    name: str | None = None
    weight: float | None = None


def build_reducer_input(responses: list[FanoutResponse], instruction: str) -> str:
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

    With names/weights (Kevin's weighted-consensus form)::

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
        parts.append("")  # blank-line separator

    parts.append("[Instruction]")
    parts.append(instruction)
    return "\n".join(parts)


def substitute_response_vars(instruction: str, entries: list[FanoutResponse]) -> str:
    """Replace ``$name`` tokens in ``instruction`` with actual response text.

    SF-90: executor-level variable substitution. After the fan-out stage
    produces N named responses, any ``$name`` reference in the reducer
    instruction is replaced with the corresponding response text.

    Only entries with a non-None ``name`` participate. Unnamed entries
    are skipped. Unknown ``$name`` references (no matching entry) are
    left as-is so the LLM sees them as literal text.

    Distinct from frontend precompilation (``$prompt``, ``$reducer``)
    which happens before the executor. Here we bind runtime results.

    Example::

        entries = [
            FanoutResponse(text="Four", name="claude"),
            FanoutResponse(text="4", name="codex"),
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


def substitute_env_vars(text: str, env: Env | None) -> str:
    """Replace ``$name`` tokens with values from the ``Env`` scope chain.

    Generalises SF-90's fan-out-only substitution to arbitrary named
    bindings (``name=`` / ``name:``) resolved via ``Env.lookup``.
    ``$item`` / ``$item.<field>`` are NOT touched (collection iteration
    owns those via ``substitute_item``). Unknown names are left verbatim.
    """
    if not text or env is None or "$" not in text:
        return text
    token = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")

    def _replace(m: re.Match) -> str:
        name = m.group(1)
        if name == "item":  # reserved: substitute_item owns $item / $item.field
            return m.group(0)
        try:
            value = env.lookup(name)
        except KeyError:
            return m.group(0)
        return value if isinstance(value, str) else str(value)

    return token.sub(_replace, text)


def split_collection_iteration(source_expr: str) -> tuple[str | None, str | None]:
    """Detect the ``source*(body)`` collection-iteration pattern.

    Scans for ``*(`` at depth 0 in the source expression. If found,
    splits into ``(collection_source, iteration_body)`` where the body
    is the content between the ``*(`` and the matching ``)``.

    Returns ``(None, None)`` when the pattern is absent.

    Examples::

        split_collection_iteration("/data/abc*(claude:/claude($item.q)!Answer)")
            → ("/data/abc", "claude:/claude($item.q)!Answer")

        split_collection_iteration("(hello, world)")
            → (None, None)     # no *( pattern
    """
    depth = 0
    for i, ch in enumerate(source_expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "*" and depth == 0:
            # Match only when followed by an opening paren.
            if i + 1 < len(source_expr) and source_expr[i + 1] == "(":
                collection_source = source_expr[:i].strip()
                body_start = i + 2  # skip past ``*(``
                body_depth = 1
                j = body_start
                while j < len(source_expr) and body_depth > 0:
                    if source_expr[j] == "(":
                        body_depth += 1
                    elif source_expr[j] == ")":
                        body_depth -= 1
                    j += 1
                if body_depth == 0:
                    return collection_source, source_expr[body_start : j - 1]
    return None, None


def substitute_item(template: str, item_json: str) -> str:
    """Replace ``$item`` / ``$item.field`` in ``template`` with values from ``item_json``.

    - ``$item`` alone → the full item string.
    - ``$item.field`` → the field value from a parsed JSON object. If
      the item isn't a JSON object or the field doesn't exist, the
      ``$item.field`` token is left as-is.
    """
    field_pattern = re.compile(r"\$item\.([a-zA-Z_][a-zA-Z0-9_]*)")
    parsed_item: dict | None = None

    def _field_replacer(match: re.Match) -> str:
        nonlocal parsed_item
        if parsed_item is None:
            try:
                parsed_item = json.loads(item_json)
            except (json.JSONDecodeError, TypeError):
                parsed_item = {}
        field = match.group(1)
        if isinstance(parsed_item, dict) and field in parsed_item:
            val = parsed_item[field]
            return val if isinstance(val, str) else json.dumps(val)
        return match.group(0)  # unknown field — leave as-is

    result = field_pattern.sub(_field_replacer, template)

    # Bare ``$item`` (not followed by ``.<fieldname>``) substitution.
    # Use a callable replacement so the item value is inserted literally — a
    # string replacement would have re interpret backslash sequences in the
    # data (e.g. ``\u`` JSON unicode escapes) and raise "bad escape", which the
    # callable form avoids (its return value is never escape-processed).
    bare_pattern = re.compile(r"\$item(?!\.[a-zA-Z_])")
    return bare_pattern.sub(lambda _match: item_json, result)


async def resolve_ensemble(items, reducer_instruction, *, processor, app, env=None):
    """Fan-out the backend-call ``items`` in parallel, then reduce via the
    ``processor`` backend using weighted-label reducer input. Returns the
    reducer's text. Dependency-neutral: imports resolve/dispatch locally so
    the AST-walker layer can call this without a circular import.
    """
    import asyncio

    from screamingface.plugins.url4_executor.url4_ast import Url4BackendCall, Url4Text
    from screamingface.plugins.url4_executor.url4_resolve import _dispatch_backend_call, resolve

    responses = list(await asyncio.gather(*[resolve(it, app, env) for it in items]))
    entries = [
        FanoutResponse(
            text=resp,
            name=it.name if isinstance(it, Url4BackendCall) else None,
            weight=it.weight if isinstance(it, Url4BackendCall) else None,
        )
        for it, resp in zip(items, responses, strict=True)
    ]
    instruction = substitute_response_vars(reducer_instruction, entries)
    reducer_input = build_reducer_input(entries, instruction)
    reducer_node = Url4BackendCall(path=processor, intent=Url4Text(value=reducer_input))
    return await _dispatch_backend_call(reducer_node, app, env)


# ---------------------------------------------------------------------------
# Legacy aliases — retained for back-compat with callers / tests that
# imported the underscore-prefixed private names before SF-108.
# ---------------------------------------------------------------------------

_ResponseEntry = FanoutResponse
_build_reducer_input = build_reducer_input
_substitute_response_vars = substitute_response_vars
_split_collection_iteration = split_collection_iteration
_substitute_item = substitute_item


__all__ = [
    "FanoutResponse",
    "_ResponseEntry",
    "_build_reducer_input",
    "_split_collection_iteration",
    "_substitute_item",
    "_substitute_response_vars",
    "build_reducer_input",
    "resolve_ensemble",
    "split_collection_iteration",
    "substitute_env_vars",
    "substitute_item",
    "substitute_response_vars",
]
