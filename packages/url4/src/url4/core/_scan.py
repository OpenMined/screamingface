"""Low-level depth-tracking scanners shared across the string decoders.

The single primitive behind url4's structure-aware parsing: track ``(``/``)``
and ``{``/``}`` nesting plus ``'…'`` quote runs (``\\'`` and ``\\\\`` escapes
honored), so callers can find balanced spans or the characters that sit outside
all nesting — spec §8 parse rule 8: only separators at depth 0 outside quotes
are structural. Kept as a dependency-free leaf (imports nothing internal) so
the parser envelope-decoders (:mod:`url4.core.parser`), the grammar
(:mod:`url4.core.grammar`), and the sub-request codec (:mod:`url4.core.subrequest`) share
one implementation instead of each carrying their own copy.
"""

from __future__ import annotations

from collections.abc import Iterator

_OPENERS = "({"
_CLOSERS = ")}"


def skip_quoted(text: str, i: int) -> int:
    """Return the index just past the quote run opening at ``i``.

    ``i`` must point at a ``'``. ``\\'`` and ``\\\\`` escapes are honored. An
    unterminated quote returns ``i + 1`` — the quote is treated as an ordinary
    literal character, preserving tolerance for malformed input. Callers can
    therefore detect the unterminated case by ``skip_quoted(t, i) == i + 1``
    (a terminated run, even the empty ``''``, always returns ``>= i + 2``).
    """
    j = i + 1
    n = len(text)
    while j < n:
        ch = text[j]
        if ch == "\\":
            j += 2
        elif ch == "'":
            return j + 1
        else:
            j += 1
    return i + 1


def iter_top_level(expr: str) -> Iterator[tuple[int, str]]:
    """Yield ``(index, char)`` for every character at depth 0 outside quotes.

    ``(``/``)`` and ``{``/``}`` track one combined nesting depth and are never
    yielded; a quote run's contents (delimiters included) are never yielded, so
    callers only see the structural characters of the current level. Depth is
    clamped at 0 — a stray closer is swallowed as structural and scanning
    continues at depth 0 (malformed-input tolerance; a stray opener swallows
    the rest, as before). An unterminated ``'`` is yielded as a literal.
    """
    depth = 0
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch == "'":
            end = skip_quoted(expr, i)
            if end == i + 1 and depth == 0:
                yield i, ch
            i = end
            continue
        if ch in _OPENERS:
            depth += 1
        elif ch in _CLOSERS:
            depth = max(depth - 1, 0)
        elif depth == 0:
            yield i, ch
        i += 1


def balanced_body(text: str, start: int) -> str | None:
    """Return the substring from ``start`` up to its matching ``)``, or None.

    ``start`` is the index just inside an already-open ``(`` (depth 1). Quote
    runs are skipped wholesale so a quoted paren cannot desync the match;
    braces are not paren-structural. Returns ``None`` if the parens never
    balance.
    """
    depth = 1
    j = start
    n = len(text)
    while j < n and depth > 0:
        ch = text[j]
        if ch == "'":
            j = skip_quoted(text, j)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        j += 1
    return text[start : j - 1] if depth == 0 else None


def find_top_level(expr: str, chars: str) -> int | None:
    """Return the index of the first depth-0 occurrence of any of ``chars``."""
    for i, ch in iter_top_level(expr):
        if ch in chars:
            return i
    return None


def split_top_level(expr: str, sep: str) -> list[str]:
    """Split ``expr`` on ``sep`` at depth 0 outside quotes; parts are stripped.

    Empty (or whitespace-only) input yields ``[]``, so callers can treat "no
    segments" and "no input" uniformly.
    """
    if not expr.strip():
        return []
    parts: list[str] = []
    last = 0
    for i, ch in iter_top_level(expr):
        if ch == sep:
            parts.append(expr[last:i])
            last = i + 1
    parts.append(expr[last:])
    return [p.strip() for p in parts]


__all__ = [
    "balanced_body",
    "find_top_level",
    "iter_top_level",
    "skip_quoted",
    "split_top_level",
]
