"""Recursive-descent parser for url4 source expressions.

This module owns the low-level :func:`parse`. It parses a *source expression* —
the part to the left of a top-level ``!`` — into the typed AST in
:mod:`url4.nodes`. The top-level ``!intent`` split, the ``;`` expression-param
envelope, and the top-level ``src*(body)`` iteration split are handled one
level up in :mod:`url4.parser` / :mod:`url4.dag.compiler`.

Why recursive descent rather than a PEG: the spec's parsing rules are
procedural and *committing*. The §4.1.1.4 structured-value classifier commits
on its first entry and MUST NOT backtrack (a post-commitment violation is
``malformed_source``, not a reclassification); ``*`` is structural only in two
exact positions (§5.3.3); and canonical-form detection scans for ``q=(`` with
an explicit rewind rule (§5.2 rule 16). Ordered-choice PEG backtracking cannot
express commitment, so the spec's numbered rules are implemented directly —
one small function per rule — on top of the depth/quote-aware scanners in
:mod:`url4._scan`.

Layering: descriptor decoding (§4.3) wraps value detection (§5.2). A source
token is first split on depth-0 ``;`` (the execution chain), the head is
classified as a bare value / ``name=`` sugar / attribution chain, and the
trailing annotations are routed by the §8.1.2 boundary algorithm — expression
params onto :class:`~url4.nodes.RelExpr` / :class:`~url4.nodes.RemoteExpr` /
:class:`~url4.nodes.Expression`, everything else onto the
:class:`~url4.nodes.Source` wrapper.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from url4._annotations import classify_boundary, extract_directives, split_annotation_pairs
from url4._scan import balanced_body, iter_top_level, skip_quoted, split_top_level
from url4.errors import ParseError
from url4.nodes import (
    Binding,
    Expression,
    IdentityRef,
    Iteration,
    IterationDirectives,
    Node,
    Params,
    RelExpr,
    RelUrl,
    RemoteExpr,
    SelfRef,
    Source,
    StructObject,
    Text,
    Url,
    VarRef,
)

_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://")
_IDENTITY_RE = re.compile(r"@(\w+)")
_VARREF_HEAD_RE = re.compile(r"\$([A-Za-z_]\w*|\d+)")
_FIELD_SEG_RE = re.compile(r"[A-Za-z_]\w*")
_INDEX_SEG_RE = re.compile(r"(0|[1-9]\d*)\]")
_STRUCT_KEY_RE = re.compile(r"[A-Za-z0-9_]+")
_STRUCT_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-]+")


def parse(text: str) -> Node:
    """Parse a url4 source expression into a typed AST node.

    Raises :class:`~url4.errors.ParseError` (code ``malformed_source``) if the
    text is not valid url4.
    """
    stripped = text.strip()
    if not stripped:
        raise ParseError("empty url4 expression")
    return _parse_source(stripped)


def parse_value(text: str) -> Node:
    """Classify ``text`` by the §5.2 value-detection rules alone (no descriptor).

    The value-position entry point for callers that already know the token is a
    data value — the builder facade uses it so a Python string is classified
    exactly as the grammar would classify it (a plain word is a bare token, a
    ``scheme://`` is a URI, …), never re-interpreted as an attribution chain.
    """
    stripped = text.strip()
    if not stripped:
        raise ParseError("empty url4 value")
    return _parse_value(stripped)


# --- source descriptors (§4.3) -------------------------------------------------


@dataclass
class _Descriptor:
    """The attribution chain decoded from a source token's head."""

    value: Node
    name: str | None = None
    kind: str = "="
    weight: float | dict | None = None
    budgets: list[tuple[str, str | dict]] = field(default_factory=list)


def _parse_source(token: str) -> Node:
    token = token.strip()
    if not token:
        raise ParseError("empty source")
    if token.startswith("*") and len(token) > 1:
        # §5.2 rule 9 — source-initial '*' is the expansion prefix; the
        # remainder undergoes full source parsing.
        return _mark_expand(_parse_source(token[1:]))
    parts = split_top_level(token, ";")
    if not parts[0]:
        raise ParseError(f"source has no value before ';' in {token!r}")
    tail = split_annotation_pairs(parts[1:])
    return _attach_tail(_parse_head(parts[0]), tail)


def _mark_expand(node: Node) -> Source:
    if isinstance(node, Source):
        return replace(node, expand=True)
    if isinstance(node, Binding):
        return Source(value=node.value, name=node.name, expand=True)
    return Source(value=node, expand=True)


def _parse_head(head: str) -> _Descriptor:
    """Decode the pre-``;`` part: bare value, ``name=`` sugar, or attrib chain.

    The sugar test runs before the bare-value test so ``article=https://x``
    binds ``article`` (§4.5) — the ``://`` inside the *value* must not promote
    the whole token to a bare URI.
    """
    if head.startswith("src="):
        result = _Descriptor(value=_parse_value(head[4:]))
    elif (sugar := _match_sugar(head)) is not None:
        result = _Descriptor(value=_parse_value(sugar[1]), name=sugar[0], kind="=")
    elif _is_value_shaped(head) or _first_colon(head) is None:
        result = _Descriptor(value=_parse_value(head))
    else:
        result = _parse_attrib_chain(head)
    return result


def _is_value_shaped(text: str) -> bool:
    """§4.3 disambiguation — a token that is a bare data value, no descriptor."""
    if text[0] in "'(/@{$":
        return True
    colon = _first_colon(text)
    return colon is not None and text[colon : colon + 3] == "://"


def _first_colon(text: str) -> int | None:
    for i, ch in iter_top_level(text):
        if ch == ":":
            return i
    return None


def _match_sugar(head: str) -> tuple[str, str] | None:
    """``name=value`` with no ``:`` before the ``=`` (§4.3 sugar form)."""
    m = _IDENT_RE.match(head)
    if m is None or head[m.end() : m.end() + 1] != "=" or len(head) == m.end() + 1:
        return None
    return m.group(), head[m.end() + 1 :]


def _parse_attrib_chain(head: str) -> _Descriptor:
    """Walk ``:``-separated attribution segments up to the data binding."""
    d = _Descriptor(value=Text(""), kind=":")
    rest = head
    first = True
    while True:
        rest = rest.strip()
        if rest.startswith("src="):
            d.value = _parse_value(rest[4:])
            return d
        if rest.startswith("(") and d.weight is None:
            # '(' in the weight position: §4.1.1.4 first-entry classification.
            struct = _classify_weight_group(rest)
            if struct is None:
                d.value = _parse_value(rest)
                return d
            d.weight, rest = struct
            first = False
            continue
        if _is_value_shaped(rest):
            d.value = _parse_value(rest)
            return d
        colon = _first_colon(rest)
        if colon is None:
            raise ParseError(
                f"bare-token data binding requires 'src=' in descriptor {head!r} (spec §4.3)"
            )
        _classify_segment(rest[:colon].strip(), first, d, head)
        rest = rest[colon + 1 :]
        first = False


def _classify_segment(seg: str, first: bool, d: _Descriptor, head: str) -> None:
    """§4.3 segment classification: name (first only), weight, or budget."""
    key, eq, val = seg.partition("=")
    if first and _IDENT_RE.fullmatch(seg) and seg != "src":
        d.name = seg
    elif _NUMBER_RE.fullmatch(seg) and d.weight is None:
        d.weight = float(seg)
    elif key == "weight" and eq and d.weight is None:
        d.weight = _parse_weight_value(val)
    elif eq and _IDENT_RE.fullmatch(key) and key not in ("src", "weight"):
        d.budgets.append((key, _parse_budget_value(val)))
    else:
        raise ParseError(f"cannot classify descriptor segment {seg!r} in {head!r}")


# --- structured annotation values (§4.1.1) --------------------------------------


def _classify_weight_group(rest: str) -> tuple[dict, str] | None:
    """Classify ``(`` in the weight position; parse a structured weight on commit.

    Returns ``(weight_mapping, remainder_after_colon)`` when the group is a
    structured annotation, or ``None`` when it begins an expression source list
    (§4.1.1.4). A committed group whose later entries violate the struct-pair
    production raises ``malformed_source`` — commitment, not a heuristic.
    """
    body = balanced_body(rest, 1)
    if body is None:
        raise ParseError(f"unclosed '(' in {rest!r}")
    if not _commits_to_struct(body):
        return None
    weight = _parse_struct_entries(body, nested=False)
    after = rest[len(body) + 2 :]
    if not after.startswith(":"):
        raise ParseError(f"structured weight must be followed by ':<data-binding>' in {rest!r}")
    return weight, after[1:]


def _commits_to_struct(body: str) -> bool:
    """§4.1.1.4 first-entry classification (True = structured annotation)."""
    entries = split_top_level(body, ",")
    if not entries or not entries[0]:
        return False
    first = entries[0]
    m = _IDENT_RE.match(first)
    if m is None or first[m.end() : m.end() + 1] != ":":
        return False  # rules 1–4, 6–7: quoted, nested, '/', '@', digit, other
    value = first[m.end() + 1 :].strip()
    if value.startswith("/"):
        result = False  # rules 5a/5b: URI scheme or relative path after ':'
    elif value.startswith("'"):
        result = all(_is_struct_pair(e) for e in entries)  # rule 5d: all-entries
    else:
        result = _is_simple_struct_value(value)  # rule 5c: commit
    return result


def _is_simple_struct_value(value: str) -> bool:
    if _NUMBER_RE.fullmatch(value) or _IDENT_RE.fullmatch(value):
        return True
    return value.startswith("(") and balanced_body(value, 1) == value[1:-1]


def _is_struct_pair(entry: str) -> bool:
    m = _STRUCT_KEY_RE.match(entry)
    if m is None or entry[m.end() : m.end() + 1] != ":":
        return False
    value = entry[m.end() + 1 :].strip()
    if value.startswith("'"):
        return skip_quoted(value, 0) == len(value) != 1
    return _is_simple_struct_value(value)


def _parse_struct_entries(body: str, *, nested: bool) -> dict:
    """Parse committed struct entries; violations are ``malformed_source``."""
    result: dict[str, object] = {}
    for entry in split_top_level(body, ","):
        m = _STRUCT_KEY_RE.match(entry)
        if m is None or entry[m.end() : m.end() + 1] != ":":
            raise ParseError(f"malformed structured annotation entry {entry!r} (spec §4.1.1.4)")
        result[m.group()] = _parse_struct_val(entry[m.end() + 1 :].strip(), nested=nested)
    if not result:
        raise ParseError("empty structured annotation value")
    return result


def _parse_struct_val(val: str, *, nested: bool) -> object:
    result: object
    if _NUMBER_RE.fullmatch(val):
        result = float(val) if "." in val else int(val)
    elif val.startswith("'"):
        result = _unquote(val)
    elif val.startswith("("):
        result = _parse_nested_struct_val(val, nested=nested)
    elif _STRUCT_TOKEN_RE.fullmatch(val):
        result = val
    else:
        raise ParseError(f"malformed structured annotation value {val!r} (spec §4.1.1.4)")
    return result


def _parse_nested_struct_val(val: str, *, nested: bool) -> dict:
    if nested:
        # §24.4.6 — at most scope → domain → scalar; deeper nesting rejected.
        raise ParseError(f"structured annotation nested too deep at {val!r}")
    inner = balanced_body(val, 1)
    if inner is None or len(inner) + 2 != len(val):
        raise ParseError(f"malformed structured annotation value {val!r}")
    return _parse_struct_entries(inner, nested=True)


def _parse_weight_value(val: str) -> float | dict:
    """The ``weight=`` reserved key: scalar or structured (§4.1.1.3)."""
    if _NUMBER_RE.fullmatch(val):
        return float(val)
    if val.startswith("("):
        inner = balanced_body(val, 1)
        if inner is not None and len(inner) + 2 == len(val):
            return _parse_struct_entries(inner, nested=False)
    raise ParseError(f"malformed weight value {val!r}")


def _parse_budget_value(val: str) -> str | dict:
    if val.startswith("("):
        inner = balanced_body(val, 1)
        if inner is not None and len(inner) + 2 == len(val):
            return _parse_struct_entries(inner, nested=False)
        raise ParseError(f"malformed structured budget value {val!r}")
    return val


# --- execution-chain routing (§4.2, §8.1.2) --------------------------------------


def _attach_tail(d: _Descriptor, tail: Params) -> Node:
    """Route the ``;`` chain and wrap the descriptor per contract."""
    value = d.value
    if isinstance(value, (RelExpr, RemoteExpr, Expression)):
        expr_params, source_ann = classify_boundary(tail)
        value = _add_expr_params(value, expr_params)
    else:
        source_ann = tail
    source_ann, expand = _extract_expand(source_ann)
    if isinstance(value, Iteration):
        source_ann, directives = _fold_directives(value, source_ann)
        if directives is not None:
            value = replace(value, directives=directives)
    if d.weight is None and not d.budgets and not source_ann and not expand:
        if d.name is not None:
            return Binding(d.name, value, "=" if d.kind == "=" else ":")
        return value
    return Source(
        value=value,
        name=d.name,
        weight=d.weight,
        budgets=tuple(d.budgets),
        annotations=source_ann,
        expand=expand,
    )


def _add_expr_params(
    value: RelExpr | RemoteExpr | Expression, params: Params
) -> RelExpr | RemoteExpr | Expression:
    return value if not params else replace(value, params=value.params + params)


def _extract_expand(annotations: Params) -> tuple[Params, bool]:
    rest = tuple(pair for pair in annotations if pair[0] != "expand")
    return rest, len(rest) != len(annotations)


def _fold_directives(
    value: Iteration, annotations: Params
) -> tuple[Params, IterationDirectives | None]:
    rest, directives = extract_directives(annotations)
    return rest, directives if len(rest) != len(annotations) else None


# --- value detection (§5.2) -------------------------------------------------------


def _parse_value(token: str) -> Node:
    token = token.strip()
    if not token:
        raise ParseError("empty value")
    star = _find_iteration_star(token)
    if star is not None:
        return _parse_iteration(token, star)
    return _dispatch_value(token)


def _dispatch_value(token: str) -> Node:
    if token.startswith("url4://"):
        node: Node = _parse_remote(token)
    elif (handler := _VALUE_HANDLERS.get(token[0])) is not None:
        node = handler(token)
    else:
        node = _var_or_bare(token)
    return node


def _var_or_bare(token: str) -> Node:
    var = _try_varref(token) if token[0] == "$" else None
    return var if var is not None else _parse_bare(token)


def _parse_quoted_value(token: str) -> Text:
    return Text(_unquote(token))


def _find_iteration_star(token: str) -> int | None:
    """The depth-0 ``*(`` iteration operator's position, if present (§5.3.3).

    Source-initial ``*`` (position 0) is the expansion prefix, not iteration —
    it is consumed in :func:`_parse_source` before value detection begins.
    """
    for i, ch in iter_top_level(token):
        if ch == "*" and i > 0 and token[i + 1 : i + 2] == "(":
            return i
    return None


# --- iteration (§5.3) ---------------------------------------------------------------


def _parse_iteration(token: str, star: int) -> Iteration:
    body = balanced_body(token, star + 2)
    if body is None:
        raise ParseError(f"unclosed iteration body in {token!r}", position=star + 1)
    after = token[star + 2 + len(body) + 1 :]
    intent: str | None = None
    if after.startswith("!"):
        intent = after[1:].strip() or None
    elif after.strip():
        raise ParseError(f"unexpected text after iteration body: {after!r}")
    return Iteration(collection=_parse_value(token[:star]), body=body.strip(), intent=intent)


# --- local expressions (§5.2 rule 1) --------------------------------------------------


def _parse_local_expr(token: str) -> Expression:
    body = balanced_body(token, 1)
    if body is None:
        raise ParseError(f"unclosed '(' in {token!r}", position=0)
    after = token[len(body) + 2 :]
    sources = _parse_group_sources(body)
    if not after:
        return Expression(sources=sources)
    if after.startswith("!*"):
        return Expression(sources=sources, intent=intent_atom(after[2:]), broadcast=True)
    if after.startswith("!"):
        return Expression(sources=sources, intent=intent_atom(after[1:]))
    raise ParseError(f"unexpected text after group: {after!r}")


def _parse_group_sources(body: str) -> tuple[Node, ...]:
    if not body.strip():
        return ()
    return tuple(_parse_source(part) for part in split_top_level(body, ","))


# --- relative and remote expressions (§5.2 rules 2–3, §3.1.1) --------------------------


def _parse_relative(token: str) -> RelUrl | RelExpr:
    pos = _find_unquoted(token, "?(")
    if pos is None:
        return RelUrl(token)
    if token[pos] == "(":
        return _parse_expr_sugar(token, pos)
    return _parse_expr_canonical(token, pos)


def _parse_expr_sugar(token: str, paren: int) -> RelExpr:
    """Sugar form ``/path(context)!intent`` (§3.1.1.1)."""
    body = balanced_body(token, paren + 1)
    if body is None:
        raise ParseError(f"unclosed '(' in {token!r}", position=paren)
    after = token[paren + 1 + len(body) + 1 :]
    return RelExpr(
        path=token[:paren],
        context=body.strip() or None,
        intent=_parse_expr_intent(after, token),
    )


def _parse_expr_canonical(token: str, qmark: int) -> RelUrl | RelExpr:
    """Canonical form ``/path?[params&]q=(context)!intent`` (§5.2 rule 7a).

    ``?`` without a ``q=(`` parameter is the rewind rule (§8 parse rule 16):
    the whole token is a relative data URI with a query string.
    """
    qstart = _find_expression_param(token, qmark)
    if qstart is None or token[qstart + 2 : qstart + 3] != "(":
        return RelUrl(token)
    body_start = qstart + 2  # past "q="
    body = balanced_body(token, body_start + 1)
    if body is None:
        raise ParseError(f"unclosed '(' in {token!r}", position=body_start)
    after = token[body_start + 1 + len(body) + 1 :]
    return RelExpr(
        path=token[:qmark],
        context=body.strip() or None,
        intent=_parse_expr_intent(after, token),
        params=_decode_query_params(token[qmark + 1 : qstart].rstrip("&")),
    )


def _find_expression_param(token: str, qmark: int) -> int | None:
    """The offset of ``q=(`` as a query parameter after ``qmark``, or None."""
    j = qmark + 1
    while j is not None:
        if token[j : j + 3] == "q=(":
            return j
        amp = _find_unquoted(token, "&", j)
        j = None if amp is None else amp + 1
    return None


def _decode_query_params(params_text: str) -> Params:
    if not params_text:
        return ()
    pairs: list[tuple[str, str | None]] = []
    for segment in params_text.split("&"):
        if segment:
            key, eq, value = segment.partition("=")
            pairs.append((key, value if eq else None))
    return tuple(pairs)


def _parse_expr_intent(after: str, token: str) -> Node | None:
    if not after:
        return None
    if after.startswith("!"):
        return intent_atom(after[1:])
    raise ParseError(f"unexpected text after expression body in {token!r}")


def _parse_remote(token: str) -> Node:
    rest = token[len("url4://") :]
    slash = rest.find("/")
    paren = _find_unquoted(rest, "(")
    if paren is not None and (slash == -1 or paren < slash):
        raise ParseError(f"remote expression requires a path: {token!r}")
    if slash == -1:
        return Url(token)
    inner = _parse_relative(rest[slash:])
    if isinstance(inner, RelUrl):
        return Url(token)  # §5.2 rule 3.3 — bare remote reference
    return RemoteExpr(
        authority=rest[:slash],
        path=inner.path,
        context=inner.context,
        intent=inner.intent,
        params=inner.params,
    )


# --- leaf values (§5.2 rules 4–10) -------------------------------------------------


def _unquote(token: str) -> str:
    """Decode a fully-quoted ``'…'`` token to its content (``\\'``/``\\\\``)."""
    end = skip_quoted(token, 0)
    if end == 1:
        raise ParseError(f"unterminated quote in {token!r}", position=0)
    if end != len(token):
        raise ParseError(f"unexpected text after quoted value in {token!r}", position=end)
    return _unescape(token[1:-1])


def _unescape(content: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(content):
        if content[i] == "\\" and i + 1 < len(content) and content[i + 1] in "\\'":
            out.append(content[i + 1])
            i += 2
        else:
            out.append(content[i])
            i += 1
    return "".join(out)


def _parse_struct_object(token: str) -> StructObject:
    end = _balanced_braces(token)
    if end is None:
        raise ParseError(f"unclosed '{{' in {token!r}", position=0)
    if token[end:].strip():
        raise ParseError(f"unexpected text after structured object in {token!r}", position=end)
    return StructObject(raw=token[:end])


def _balanced_braces(token: str) -> int | None:
    depth = 0
    i = 0
    while i < len(token):
        ch = token[i]
        if ch == "'":
            i = skip_quoted(token, i)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _parse_reference(token: str) -> SelfRef | IdentityRef:
    """``@`` / ``@name[/collection]`` (§5.2 rule 7, §5.6.2)."""
    if token == "@":
        return SelfRef()
    m = _IDENTITY_RE.match(token)
    if m is None:
        raise ParseError(f"invalid reference {token!r} (spec §5.6.2)")
    rest = token[m.end() :]
    if not rest:
        return IdentityRef(m.group(1))
    if rest.startswith("/"):
        collection = rest[1:]
        segments = collection.split("/")
        if all(seg and " " not in seg for seg in segments):
            return IdentityRef(m.group(1), collection)
    raise ParseError(f"invalid identity reference {token!r} (spec §5.6.2)")


def _try_varref(token: str) -> VarRef | None:
    """A standalone ``$name[.field][N]`` reference consuming the whole token.

    Partial consumption (e.g. ``$a b`` or ``$$x``) is not a structural
    reference — the token stays a bare value and the interpolation phase
    (spec §8.2) handles any embedded references at resolve time.
    """
    m = _VARREF_HEAD_RE.match(token)
    if m is None:
        return None
    path: list[str | int] = []
    i = m.end()
    while i < len(token):
        step = _varref_segment(token, i, path)
        if step is None:
            break
        i = step
    return VarRef(m.group(1), tuple(path)) if i == len(token) else None


def _varref_segment(token: str, i: int, path: list[str | int]) -> int | None:
    result: int | None = None
    if token[i] == ".":
        seg = _FIELD_SEG_RE.match(token, i + 1)
        if seg is not None:
            path.append(seg.group())
            result = seg.end()
    elif token[i] == "[":
        # '[' not followed by digits ends the path (§8 rule 17b).
        idx = _INDEX_SEG_RE.match(token, i + 1)
        if idx is not None:
            path.append(int(idx.group(1)))
            result = idx.end()
    return result


def _parse_bare(token: str) -> Text | Url:
    """Bare-value consumption (§5.2 rules 5/10): any-scheme URI or plain text.

    Balanced ``(…)`` runs are tolerated inside URIs (``/wiki/Fish_(animal)``),
    preserving the pre-0.2 tolerance; in plain text a paren is structural and
    must be quoted (spec §7.2).
    """
    is_uri = _SCHEME_RE.match(token) is not None
    i = 0
    while i < len(token):
        ch = token[i]
        if ch == "'":
            i = skip_quoted(token, i)
        elif ch == "(" and is_uri:
            body = balanced_body(token, i + 1)
            if body is None:
                raise ParseError(f"unclosed '(' in {token!r}", position=i)
            i += len(body) + 2
        elif ch in "()":
            raise ParseError(f"unexpected {ch!r} in bare value {token!r}", position=i)
        else:
            i += 1
    return Url(token) if is_uri else Text(token)


def _find_unquoted(text: str, chars: str, start: int = 0) -> int | None:
    """The first occurrence of any of ``chars`` outside quote runs (parens seen)."""
    i = start
    while i < len(text):
        if text[i] == "'":
            i = skip_quoted(text, i)
            continue
        if text[i] in chars:
            return i
        i += 1
    return None


# Dispatch by value-initial character (§5.2); populated after the handlers so
# the names are bound. ``url4://`` is tested before this table (it starts with
# a plain letter).
_VALUE_HANDLERS: dict[str, Callable[[str], Node]] = {
    "(": _parse_local_expr,
    "/": _parse_relative,
    "'": _parse_quoted_value,
    "{": _parse_struct_object,
    "@": _parse_reference,
}


def intent_atom(intent: str) -> Node:
    """Classify a raw intent string into a leaf AST node (§6).

    Quoted → :class:`~url4.nodes.Text` content (quotes are delimiters);
    ``/path`` → :class:`~url4.nodes.RelUrl`; any ``scheme://…`` →
    :class:`~url4.nodes.Url`; anything else → :class:`~url4.nodes.Text`.
    """
    text = intent.strip()
    if text.startswith("'"):
        node: Node = Text(_unquote(text))
    elif _SCHEME_RE.match(text) is not None:
        node = Url(text)
    elif text.startswith("/"):
        node = RelUrl(text)
    else:
        node = Text(text)
    return node


__all__ = ["intent_atom", "parse", "parse_value"]
