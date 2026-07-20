"""Shared ``;``-chain decoding: annotation pairs, iteration directives, and the
§8.1.2 expression/source boundary.

Both the grammar (:mod:`url4.grammar`, for ``;`` tails on individual sources)
and the envelope decoders (:mod:`url4.parser`, for top-level trailing params)
need the same three pieces of logic; this dependency-free leaf holds the single
definition so the two layers cannot drift:

- :func:`split_annotation_pairs` — ``;key[=value]`` chain → ordered pairs.
- :func:`extract_directives` — pull ``iteration.*`` keys (and their deprecated
  ``foreach.*`` spellings) out of a pair list into
  :class:`~url4.nodes.IterationDirectives`, validating values.
- :func:`classify_boundary` — the §8.1.2 desugaring algorithm: expression-level
  params are consumed greedily until the first *exclusively source-level* key;
  everything from that key on is a source-level execution annotation.
"""

from __future__ import annotations

import warnings

from url4.core.errors import ParseError
from url4.core.nodes import IterationDirectives, Params

# §8.1.3 — keys that can ONLY be source-level execution annotations; the first
# one encountered in a sugar-form ``;`` chain triggers the boundary. ``coord.*``
# and ``iteration.*`` prefixes are matched separately.
EXCLUSIVE_SOURCE_KEYS = frozenset(
    {"mode", "retry", "required", "optional", "accept", "expand", "coord"}
)

_VALID_ON_ERROR = ("skip", "fail", "collect")


def split_annotation_pairs(parts: list[str]) -> Params:
    """Decode raw ``key[=value]`` segments into ordered pairs (flags → None)."""
    pairs: list[tuple[str, str | None]] = []
    for part in parts:
        key, eq, value = part.strip().partition("=")
        pairs.append((key.strip(), value.strip() if eq else None))
    return tuple(pairs)


def is_source_level_key(key: str) -> bool:
    """True for keys that are exclusively source-level (§8.1.3 boundary set)."""
    return key in EXCLUSIVE_SOURCE_KEYS or key.startswith(("coord.", "iteration.", "foreach."))


def classify_boundary(pairs: Params) -> tuple[Params, Params]:
    """Split a sugar-form ``;`` chain into (expression params, source annotations).

    §8.1.2/§8.1.3: params are expression-level until the first exclusively
    source-level key; that key and everything after it are source-level. Dual
    keys (``t``, ``ct_mismatch``, ``budget_mode``, ``broadcast``) classify by
    which side of the boundary they fall on.
    """
    expr_params: list[tuple[str, str | None]] = []
    source_ann: list[tuple[str, str | None]] = []
    boundary = False
    for key, value in pairs:
        boundary = boundary or is_source_level_key(key)
        (source_ann if boundary else expr_params).append((key, value))
    return tuple(expr_params), tuple(source_ann)


def extract_directives(pairs: Params) -> tuple[Params, IterationDirectives]:
    """Pull ``iteration.*`` / deprecated ``foreach.*`` keys out of ``pairs``.

    Returns the remaining pairs plus the decoded directives. Unknown
    ``iteration.<key>`` names are ignored (forward compatibility), matching the
    pre-0.2 tolerance for unknown ``foreach.*`` keys.
    """
    rest: list[tuple[str, str | None]] = []
    fields: dict[str, object] = {}
    for key, value in pairs:
        name = _directive_name(key)
        if name is None:
            rest.append((key, value))
        elif name in ("concurrency", "on_error", "slice", "fmt_result"):
            fields[name] = _parse_directive(name, value or "")
    return tuple(rest), IterationDirectives(**fields)  # type: ignore[arg-type]


def _directive_name(key: str) -> str | None:
    """The directive field for ``key``, or None; warns on deprecated spellings."""
    if key.startswith("iteration."):
        return key[len("iteration.") :]
    if key.startswith("foreach."):
        warnings.warn(
            f"';{key}=' is deprecated; use ';iteration.{key[8:]}='",
            DeprecationWarning,
            stacklevel=4,
        )
        return key[len("foreach.") :]
    return None


def _parse_directive(name: str, value: str) -> object:
    parser = {"concurrency": _parse_concurrency, "on_error": _parse_on_error}.get(name)
    if parser is None:
        return _parse_slice(value) if name == "slice" else value.strip()  # fmt_result
    return parser(value)


def _parse_on_error(value: str) -> str:
    result = value.strip()
    if result == "abort":
        warnings.warn(
            "iteration.on_error=abort is deprecated; use =fail",
            DeprecationWarning,
            stacklevel=5,
        )
        return "fail"
    if result not in _VALID_ON_ERROR:
        raise ParseError(
            f"invalid iteration.on_error={result!r}; expected one of {', '.join(_VALID_ON_ERROR)}"
        )
    return result


def _parse_concurrency(value: str) -> int:
    """A ``iteration.concurrency`` value; must be a positive int (unbounded is
    expressed by omitting the directive)."""
    try:
        n = int(value)
    except ValueError:
        raise ParseError(
            f"invalid iteration.concurrency={value.strip()!r}; expected a positive integer"
        ) from None
    if n < 1:
        raise ParseError(f"invalid iteration.concurrency={n}; must be >= 1")
    return n


def _parse_slice(value: str) -> tuple[int, int]:
    """A ``iteration.slice`` value: the half-open ``start:end`` element range."""
    start_text, sep, end_text = value.partition(":")
    try:
        if not sep:
            raise ValueError
        start, end = int(start_text), int(end_text)
    except ValueError:
        raise ParseError(
            f"invalid iteration.slice={value.strip()!r}; expected 'start:end' integers"
        ) from None
    if start < 0 or end < start:
        raise ParseError(f"invalid iteration.slice={value.strip()!r}; need 0 <= start <= end")
    return start, end


__all__ = [
    "EXCLUSIVE_SOURCE_KEYS",
    "classify_boundary",
    "extract_directives",
    "is_source_level_key",
    "split_annotation_pairs",
]
