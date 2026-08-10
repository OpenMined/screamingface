"""Strict HTTP-status validation shared across core and provider plugins.

Provider-neutral: the one place that decides whether an upstream-supplied value
is a usable HTTP error status. Consolidates three previously-divergent copies
(OME-428 third-review blocker E).
"""

from __future__ import annotations


def valid_http_error_status(value: object) -> int | None:
    """Return ``value`` when it is a real HTTP error status (400-599), else None.

    # INVARIANT: exactly ``type(value) is int and 400 <= value <= 599``.
    # WHY: ``type(... ) is int`` (not ``isinstance``) rejects ``bool`` — a
    # ``True``/``False`` is an ``int`` subclass and ``int(True) == 1`` is not a
    # status. Strings, floats (incl. ``nan``/``inf``), and ``Decimal`` are all
    # rejected: the OpenRouter ``error.code`` schema is integer-only, and
    # ``"²".isdigit()`` is True while ``int("²")`` raises ValueError (the exact
    # crash-to-500 this validator exists to prevent), while a fullwidth
    # ``"４２９"`` would otherwise be silently coerced to 429.
    """
    if type(value) is int and 400 <= value <= 599:
        return value
    return None


def valid_http_status(value: object) -> int | None:
    """Return ``value`` when it is any real HTTP status (100-599), else None.

    The same strictness as ``valid_http_error_status`` (see its INVARIANT) over the
    full status range, for callers that must also accept success and redirect codes.

    # WHY a sibling rather than a parameter on the function above: that function's
    # name is its contract at ~40 call sites which all mean "is this an ERROR status".
    # Widening its range behind a default would silently admit a 200 at every one of
    # them. OME-303 observes real transport responses, so it needs 2xx and 3xx too.
    """
    if type(value) is int and 100 <= value <= 599:
        return value
    return None
