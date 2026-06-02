"""URL4 expression utilities."""

from __future__ import annotations

from dataclasses import dataclass


def split_intent(expr: str) -> tuple[str, str | None, bool]:
    """Split on outermost ``!`` or ``!*`` (outside balanced parens).

    Returns ``(source_expression, intent, broadcast)`` where:

    - *source_expression* is the part before the ``!``
    - *intent* is the part after the ``!`` (or ``!*``), or ``None``
    - *broadcast* is ``True`` when the operator was ``!*`` (SF-93
      intent broadcasting), ``False`` for regular ``!``

    Backend-call awareness (SF-79 Stage B): a ``!`` immediately preceded
    by ``()`` is treated as part of a backend_call's intent tail, not as
    a top-level intent separator.

    SF-93 intent broadcasting: ``!*`` tells the executor to apply the
    intent independently to EACH source in a list. Results are collected
    into a newline-separated output.

    Examples::

        split_intent("(a, b)!summarize")
            → ("(a, b)", "summarize", False)

        split_intent("(a, b)!*uppercase")
            → ("(a, b)", "uppercase", True)   # broadcast mode

        split_intent("/claude()!hello")
            → ("/claude()!hello", None, False)  # backend_call, not split
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
            # Check for !* (broadcast operator)
            if i + 1 < len(expr) and expr[i + 1] == "*":
                return expr[:i], expr[i + 2 :], True
            return expr[:i], expr[i + 1 :], False
    return expr, None, False


@dataclass(frozen=True)
class ForeachDirectives:
    """Execution annotations for collection iteration (``;foreach.*``)."""

    concurrency: int | None = None
    on_error: str = "abort"  # "abort" (default) | "collect"


def split_foreach_annotations(expr: str) -> tuple[str, ForeachDirectives]:
    """Strip trailing ``;foreach.<key>=<value>`` directives (outside parens).

    Returns ``(clean_expr, ForeachDirectives)``. Only ``;`` at paren-depth 0
    is treated as a directive separator; unknown keys are ignored.
    """
    depth = 0
    cut = len(expr)
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ";" and depth == 0:
            cut = i
            break
    if cut == len(expr):
        return expr, ForeachDirectives()

    clean = expr[:cut].strip()
    concurrency: int | None = None
    on_error = "abort"
    for part in expr[cut + 1 :].split(";"):
        part = part.strip()
        if part.startswith("foreach.concurrency="):
            try:
                concurrency = int(part.split("=", 1)[1])
            except ValueError:
                concurrency = None
        elif part.startswith("foreach.on_error="):
            on_error = part.split("=", 1)[1].strip()
    return clean, ForeachDirectives(concurrency=concurrency, on_error=on_error)
