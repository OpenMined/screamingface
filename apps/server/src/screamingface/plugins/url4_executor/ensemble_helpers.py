"""Helper functions for the ensemble interpreter.

Extracted from :mod:`ensemble` during SF-108 so the interpreter itself
can shrink to a thin dispatch over the four evaluation strategies
(collection iteration, broadcast, ensemble fan-out, single-source).

Public names (unprefixed): ``FanoutResponse``, ``build_reducer_input``,
``substitute_response_vars``, ``split_collection_iteration``,
``substitute_item``. The legacy underscore-prefixed aliases are kept
for back-compat with existing callers and tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from screamingface.plugins.url4_executor.scope import Env

# Identifier-shaped ``$<name>`` token. ``\b`` on the right prevents
# ``$consensus`` from matching the prefix of ``$consensus_thing``.
_NAME_REF_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)\b")


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


def substitute_env_vars(text: str, env: Env | None) -> str:
    """Replace every ``$<name>`` in ``text`` via ``env.lookup(name)``.

    DEMO-006 (SF-149): read side of DEMO-005 bindings. Unknown names
    are left literal — matches ``substitute_response_vars`` behaviour
    so LLMs see surprising tokens as text rather than errors.

    Non-string values are JSON-encoded (matches ``substitute_item``).
    """
    if not text or env is None:
        return text

    def _repl(match: re.Match) -> str:
        name = match.group(1)
        try:
            value = env.lookup(name)
        except KeyError:
            return match.group(0)
        return value if isinstance(value, str) else json.dumps(value)

    return _NAME_REF_RE.sub(_repl, text)


def substitute_response_vars(
    instruction: str,
    entries: list[FanoutResponse],
    env: Env | None = None,
) -> str:
    """Replace ``$name`` tokens in ``instruction`` with bound values.

    SF-90 + DEMO-006 (SF-149): unified ``$<name>`` resolution.

    Lookup order per token:

    1. ``env.lookup(name)`` — DEMO-005 bindings (named scope frames)
    2. Matching ``FanoutResponse.name`` in ``entries`` — legacy ensemble
       fan-out behaviour
    3. Leave the token literal — the LLM sees it as text

    Step 3 is intentional. Existing tests rely on missing references
    passing through unchanged. Non-string env values are JSON-encoded
    (matches :func:`substitute_item`).
    """
    if not instruction:
        return instruction

    entry_map: dict[str, str] = {e.name: e.text.strip() for e in entries if e.name is not None}

    def _repl(match: re.Match) -> str:
        name = match.group(1)
        if env is not None:
            try:
                value = env.lookup(name)
            except KeyError:
                pass
            else:
                return value if isinstance(value, str) else json.dumps(value)
        if name in entry_map:
            return entry_map[name]
        return match.group(0)

    return _NAME_REF_RE.sub(_repl, instruction)


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
    """Replace ``$item`` / ``$item.a.b.c`` in ``template`` with values from ``item_json``.

    - ``$item`` alone → the full ``item_json`` string.
    - ``$item.a.b.c`` (one or more segments) → walks the parsed JSON
      dict recursively. If any intermediate value isn't a dict, or a
      segment is missing, the whole ``$item.a.b.c`` token stays
      literal. Terminal non-string values are JSON-encoded (matches
      the original single-level behaviour).
    """
    field_pattern = re.compile(r"\$item((?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)")
    parsed_item: dict | None = None
    parse_attempted = False

    def _ensure_parsed() -> None:
        nonlocal parsed_item, parse_attempted
        if parse_attempted:
            return
        parse_attempted = True
        try:
            loaded = json.loads(item_json)
        except (json.JSONDecodeError, TypeError):
            parsed_item = None
            return
        parsed_item = loaded if isinstance(loaded, dict) else None

    def _field_replacer(match: re.Match) -> str:
        _ensure_parsed()
        if parsed_item is None:
            return match.group(0)
        segments = match.group(1).split(".")[1:]  # drop the leading empty slot
        cursor: object = parsed_item
        for seg in segments:
            if not isinstance(cursor, dict) or seg not in cursor:
                return match.group(0)
            cursor = cursor[seg]
        return cursor if isinstance(cursor, str) else json.dumps(cursor)

    result = field_pattern.sub(_field_replacer, template)

    # Bare ``$item`` (not followed by ``.<identifier>``) substitution.
    bare_pattern = re.compile(r"\$item(?!\.[a-zA-Z_])")
    return bare_pattern.sub(item_json, result)


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
    "split_collection_iteration",
    "substitute_env_vars",
    "substitute_item",
    "substitute_response_vars",
]
