"""URL4 expression utilities."""

from __future__ import annotations


def split_intent(expr: str) -> tuple[str, str | None]:
    """Split on outermost ``!`` (outside balanced parens).

    Returns ``(source_expression, intent)`` or ``(expr, None)`` if no intent.

    Backend-call awareness (SF-79 Stage B): a ``!`` immediately preceded
    by ``()`` is treated as part of a backend_call's intent tail, not as
    a top-level intent separator. This makes the user-friendly form
    ``/claude()!hello`` parse as a single backend_call rather than
    splitting into ``source=/claude()`` + ``intent=hello`` (which would
    leave the backend with an empty prompt).

    Examples::

        split_intent("/claude()!hello")
            → ("/claude()!hello", None)   # NEW: not split, the whole
                                          # thing is a backend_call

        split_intent("(/claude()!a, /claude()!b)!reduce")
            → ("(/claude()!a, /claude()!b)", "reduce")  # outer ! has
                                          # ')e' preceding, not '()'

        split_intent("(/claude())!reduce")
            → ("(/claude())", "reduce")   # ! has '))' preceding, splits

        split_intent("(https://ex.com)!summarize")
            → ("(https://ex.com)", "summarize")  # unchanged
    """
    depth = 0
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "!" and depth == 0:
            # If the ! is immediately preceded by '()', it belongs to a
            # backend_call (``/path()!intent``) and is NOT a top-level
            # intent separator. Skip it and keep scanning.
            if i >= 2 and expr[i - 2 : i] == "()":
                continue
            return expr[:i], expr[i + 1 :]
    return expr, None
