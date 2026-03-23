"""URL4 expression utilities."""

from __future__ import annotations


def split_intent(expr: str) -> tuple[str, str | None]:
    """Split on outermost ``!`` (outside balanced parens).

    Returns ``(source_expression, intent)`` or ``(expr, None)`` if no intent.
    """
    depth = 0
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "!" and depth == 0:
            return expr[:i], expr[i + 1:]
    return expr, None
