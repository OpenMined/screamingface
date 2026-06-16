"""Pretty-formatter for url4 expressions.

Produces a canonical, indented layout. Mirrors the EnsembleInterpreter's
*string-level* decomposition (``split_intent`` → ``split_foreach_annotations``
→ ``split_collection_iteration``) rather than the base TatSu grammar, because
the base grammar can't parse the ensemble envelope (``;foreach`` / fan-out) —
see the dispatcher in ``ensemble.py`` and the SF-251 highlight gap.

Layout rules:
- ``,``-separated list items: one per line at the current indent.
- ``(`` groups nest at +2 spaces; ``)`` closes at the group's indent.
- ``!<intent>`` and each ``;foreach.*`` directive start on their own line.
- ``{...}`` json-blob intents are pretty-printed (json, indent=2).
- string literals (``'…'``) are left byte-identical (soft-wrap is a display
  concern, never a content rewrite).
"""

from __future__ import annotations

import json

from screamingface.plugins.url4_executor.decoder import (
    ForeachDirectives,
    split_foreach_annotations,
    split_intent,
)
from screamingface.plugins.url4_executor.ensemble_helpers import split_collection_iteration

INDENT = 2


def format_url4(expr: str) -> str:
    """Format a url4 expression. Raises on malformed bracket/quote nesting."""
    return _format(expr, 0)


def format_url4_safe(expr: str) -> tuple[str, str | None]:
    """Format, returning ``(formatted, None)`` or ``(original, error)`` on failure.

    Never raises and never destroys input — callers can show the error and keep
    the user's text.
    """
    try:
        return format_url4(expr), None
    except Exception as exc:  # noqa: BLE001 — formatting must never lose the user's input
        return expr, str(exc)


def _pad(indent: int) -> str:
    return " " * indent


def _split_top_level(s: str, sep: str) -> list[str]:
    """Split ``s`` on ``sep`` only at paren/brace depth 0 and outside quotes."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    for i, ch in enumerate(s):
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(s[start:i])
            start = i + 1
    parts.append(s[start:])
    return parts


def _strip_one_paren_layer(expr: str) -> str | None:
    """If ``expr`` is exactly one balanced ``(...)`` group, return its interior; else None."""
    e = expr.strip()
    if not (e.startswith("(") and e.endswith(")")):
        return None
    depth = 0
    for i, ch in enumerate(e):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and i != len(e) - 1:
                return None
    return e[1:-1]


def _collapse_ws(s: str) -> str:
    """Collapse whitespace runs to single spaces, outside quoted literals."""
    out: list[str] = []
    quote: str | None = None
    prev_space = False
    for ch in s:
        if quote is not None:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            prev_space = False
        elif ch.isspace():
            if not prev_space:
                out.append(" ")
            prev_space = True
        else:
            out.append(ch)
            prev_space = False
    return "".join(out).strip()


def _directive_lines(directives: ForeachDirectives) -> list[str]:
    lines: list[str] = []
    if directives.concurrency is not None:
        lines.append(f";foreach.concurrency={directives.concurrency}")
    if directives.on_error != "abort":
        lines.append(f";foreach.on_error={directives.on_error}")
    return lines


def _format_intent(intent: str, indent: int) -> str:
    intent = intent.strip()
    if intent.startswith("{"):
        try:
            obj = json.loads(intent)
            pretty = json.dumps(obj, indent=INDENT, ensure_ascii=False)
            return pretty.replace("\n", "\n" + _pad(indent))
        except (json.JSONDecodeError, ValueError):
            pass  # not valid JSON (or has substitutions) — leave verbatim
    # Quoted strings and other intents are left byte-identical (no hard-wrap).
    return intent


def _format(expr: str, indent: int) -> str:
    expr = expr.strip()
    if not expr:
        return ""

    # A top-level comma list (e.g. a group interior or iteration body): one item per line.
    parts = _split_top_level(expr, ",")
    if len(parts) > 1:
        sep = ",\n" + _pad(indent)
        return sep.join(_format(p.strip(), indent) for p in parts)

    source, intent, broadcast = split_intent(expr)
    source, directives = split_foreach_annotations(source)

    out = _render_source(source.strip(), indent)
    for line in _directive_lines(directives):
        out += "\n" + _pad(indent) + line
    if intent is not None:
        bang = "!*" if broadcast else "!"
        out += "\n" + _pad(indent) + bang + _format_intent(intent, indent)
    return out


def _render_source(source: str, indent: int) -> str:
    if not source:
        return ""

    # Collection iteration: SOURCE*(BODY)
    coll_src, body = split_collection_iteration(source)
    if coll_src is not None and body is not None:
        inner = _format(body.strip(), indent + INDENT)
        return (
            f"{_render_source(coll_src.strip(), indent)}*(\n"
            f"{_pad(indent + INDENT)}{inner}\n{_pad(indent)})"
        )

    # Named binding wrapping a group: name=( … ) or name:( … )
    for op in ("=", ":"):
        head, sep, rest = source.partition(op)
        if sep and head.isidentifier() and _strip_one_paren_layer(rest) is not None:
            return f"{head}{op}{_render_source(rest.strip(), indent)}"

    # A balanced ( … ) group.
    interior = _strip_one_paren_layer(source)
    if interior is not None:
        inner = _format(interior.strip(), indent + INDENT)
        return f"(\n{_pad(indent + INDENT)}{inner}\n{_pad(indent)})"

    # Leaf (backend call, url, weighted source, etc.) — single line, ws collapsed.
    return _collapse_ws(source)
