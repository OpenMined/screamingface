"""Exception hierarchy for the url4 core library.

This module is a dependency-free sink: every other module may import it, and it
imports nothing internal. Keeping it isolated prevents import cycles.

The hierarchy mirrors the phases of evaluation so callers can catch broadly
(:class:`Url4Error`) or narrowly (a specific failure mode):

- :class:`ParseError`     — the expression text is not valid url4 (grammar).
- :class:`ScopeError`     — a ``$name`` / ``$N`` reference is unbound (context).
- :class:`ResolutionError`— a source could not be resolved (I/O layer).
- :class:`CollectionError`— a ``*`` collection source is not iterable.
- :class:`CycleError`     — a hand-built node graph contains a dependency cycle.

Every error additionally carries the spec's wire-level vocabulary: ``code`` is
the error-code string a node reports (e.g. ``malformed_source``, spec Part B/C)
and ``permanent`` marks whether retrying can ever succeed (permanent errors
MUST NOT be retried). Subclasses set class-level defaults; both can be
overridden per instance for spec codes that share a Python type — e.g.
``unknown_identity`` or ``expansion_not_iterable`` raised as a
:class:`ResolutionError`/:class:`CollectionError` with an explicit ``code``.
"""

from __future__ import annotations


class Url4Error(Exception):
    """Base class for every error raised by the url4 library."""

    code: str = "internal_error"
    permanent: bool = True

    def __init__(
        self, message: str, *, code: str | None = None, permanent: bool | None = None
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if permanent is not None:
            self.permanent = permanent


class ParseError(Url4Error):
    """The expression could not be parsed into an AST.

    ``position`` is the 0-based character offset into the source expression at
    which parsing failed, or ``None`` when the underlying parser did not report
    one.
    """

    code = "malformed_source"

    def __init__(
        self,
        message: str,
        *,
        position: int | None = None,
        code: str | None = None,
        permanent: bool | None = None,
    ) -> None:
        super().__init__(message, code=code, permanent=permanent)
        self.position = position


class ScopeError(Url4Error):
    """A ``$name`` or ``$N`` variable reference could not be resolved in scope."""

    code = "unbound_reference"


class ResolutionError(Url4Error):
    """A source (URL, relative path, or sub-request) failed to resolve.

    Transient by default — an I/O failure may succeed on retry. Permanent
    resolution outcomes (``unknown_identity``, ``identity_access_denied``, …)
    are raised with explicit ``code=…, permanent=True``.
    """

    code = "resolution_failed"
    permanent = False


class CollectionError(Url4Error):
    """A ``*`` collection source did not resolve to a usable, iterable value."""

    code = "malformed_source"


class CycleError(Url4Error):
    """A node graph contains a dependency cycle and cannot be executed.

    Compiler-emitted graphs are acyclic by construction; this guards graphs
    assembled by hand from custom nodes.
    """

    code = "cycle_detected"


class RenderError(Url4Error):
    """An AST node cannot be rendered as url4 text that reparses to itself.

    Raised by :func:`url4.render.render` for values the grammar cannot carry
    (a bare URI with unbalanced parens or depth-0 separators, a negative
    weight, over-deep structured annotations) and for node shapes whose
    rendered form would reparse differently (spec §8.1.2 boundary hazards,
    a nested reduce-over-iteration).
    """

    code = "unrenderable"


__all__ = [
    "CollectionError",
    "CycleError",
    "ParseError",
    "RenderError",
    "ResolutionError",
    "ScopeError",
    "Url4Error",
]
