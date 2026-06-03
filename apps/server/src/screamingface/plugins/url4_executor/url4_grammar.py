"""TatSu PEG grammar + semantics for the url4 protocol.

The grammar string and the :class:`Url4Semantics` class were extracted
from the original ``url4.py`` so consumers that only need :func:`parse`
don't pull in the resolution side (httpx, plugin registry, etc).
"""

from __future__ import annotations

from tatsu import compile

from screamingface.plugins.url4_executor.url4_ast import (
    Url4BackendCall,
    Url4Binding,
    Url4ExpandedSource,
    Url4List,
    Url4Node,
    Url4RelUrl,
    Url4Text,
    Url4Url,
)

GRAMMAR = r"""
    @@grammar::Url4
    @@whitespace :: //

    start = context $ ;

    context
        = group
        | atom
        ;

    group = '(' elems:','%{ context } ')' ;

    atom
        = binding
        | backend_call
        | expanded_source
        | url
        | relurl
        | text
        ;

    # DEMO-005 (SF-152): named bindings.
    #
    #   name=expr   — eager value bind. RHS is any atom or a group.
    #   name:(...)  — subexpression label. RHS is always a group.
    #
    # Placed before backend_call so a binding takes precedence in the
    # alternative list. Disambiguation with source_label (`name:NUMBER:`)
    # works because the `:` branch of binding requires `(` next, while
    # source_label requires a digit next — they cannot collide.
    #
    # TODO(SF-152): the bare `name:/path` (no weight) form on a backend
    # call still parses as text + relurl. Fixing it conflicts with the
    # URL scheme separator and is out of scope here.
    binding
        = name:/[a-zA-Z_][a-zA-Z0-9_]*/ (
              sep:'=' value:eq_value
            | sep:':' value:group
          )
        ;

    # RHS of `name=`. Spec says "any atom (text, URL, group, backend
    # call)" — so groups are allowed too. Excludes nested bindings to
    # avoid `a=b=c` ambiguity (a group containing a binding is fine
    # because a Url4List frame sits between the outer and inner bind).
    eq_value
        = group
        | atom_no_binding
        ;

    atom_no_binding
        = backend_call
        | expanded_source
        | url
        | relurl
        | text
        ;

    # SF-92: Source expansion — *source expands a collection into
    # individual sources. The * prefix tells the executor to fetch
    # the source, parse it as a collection (JSON/JSONL/CSV), and
    # treat each item as a separate source.
    expanded_source = '*' inner:expandable_atom ;

    # Atoms that can follow * — same as atom minus expanded_source
    # itself (no **source) and minus backend_call (no */claude()).
    expandable_atom
        = url
        | relurl
        | text
        ;

    # Backend-call form: [name:weight:]path(context)!<intent>
    #
    # Recognizes a plugin/backend invocation shorthand where:
    # - ``name:weight:`` is an optional prefix labeling the source
    #   (e.g. ``claude:40:`` for 40% weight). Used by the ensemble
    #   reducer to format weighted responses. (SF-88)
    # - ``/path`` is the backend route (``/claude``, ``/codex``, etc.)
    # - ``(context)`` carries optional inline context (SF-89)
    # - ``!<intent>`` is the LLM instruction for that backend
    #
    # The intent is any atom EXCEPT another backend_call.
    backend_call
        = [ label:source_label ] path:backend_path
          '(' [ packed_context:backend_context ] ')'
          [ '!' intent:atom_no_bc ]
        ;

    # Optional name:weight: prefix for named/weighted fan-out.
    # Format: name:weight: where name is [a-zA-Z_][a-zA-Z0-9_]* and
    # weight is an integer or decimal number.
    # The trailing colon before the path is included so /path is
    # unambiguous (path always starts with /).
    source_label = name:/[a-zA-Z_][a-zA-Z0-9_]*/ ':' weight:/[0-9]+(?:\.[0-9]+)?/ ':' ;

    # Content inside backend call parens. Matches any non-paren chars
    # (including commas, bangs, slashes, etc.) as raw text. Nested parens
    # are NOT supported in context packing Phase 1 — use /data/<key>
    # references for complex content.
    backend_context = /[^()]+/ ;

    # Path prefix for a backend_call: starts with /, continues until
    # the first '(' or ',' or whitespace or '!'. Also excludes URL
    # query/fragment chars ('?', '&', '#') so that URLs like
    # ``/claude?q=()`` don't get captured as backend_call paths — those
    # stay as regular URL fetches (Url4RelUrl).
    backend_path = /\/[^\s,()!?&#]+/ ;

    # atom alternatives used INSIDE a backend_call intent — excludes
    # backend_call itself to avoid ambiguous nesting. ``/claude()!a`` is a
    # single backend_call; ``/claude()!/other()!b`` puts ``/other()!b`` as
    # the intent (a relurl, since intent can't contain another backend_call).
    atom_no_bc
        = url
        | relurl
        | json_blob
        | quoted
        | text
        ;

    url = value:/https?:\/\/(?:[^\s,()]|\([^()]*\))+/ ;

    relurl = value:/\/(?:[^\s,()]|\([^()]*\))*/ ;

    text = value:/[^,()]+/ ;

    # A JSON-object intent payload: balanced { ... } allowing one level of
    # nested {}. Lets a backend-call intent carry a multi-key JSON payload
    # whose internal commas would otherwise split the enclosing list.
    json_blob = value:/\{(?:[^{}]|\{[^{}]*\})*\}/ ;

    # A quoted-string intent: '…' or "…" — commas inside are part of the
    # string, not list separators. Twin of json_blob for quoted prompts.
    quoted = value:/'[^']*'|"[^"]*"/ ;
"""


class Url4Semantics:
    def url(self, ast):
        return Url4Url(value=ast.value.strip())

    def relurl(self, ast):
        return Url4RelUrl(value=ast.value.strip())

    def text(self, ast):
        return Url4Text(value=ast.value.strip())

    def json_blob(self, ast):
        return Url4Text(value=ast.value.strip())

    def quoted(self, ast):
        return Url4Text(value=ast.value.strip())

    def backend_call(self, ast):
        packed = getattr(ast, "packed_context", None)
        if isinstance(packed, str):
            packed = packed.strip() or None

        label = getattr(ast, "label", None)
        name = None
        weight = None
        if label and isinstance(label, dict):
            name = label.get("name")
            weight_str = label.get("weight")
            if weight_str is not None:
                try:
                    weight = float(weight_str)
                except (ValueError, TypeError):
                    weight = None

        return Url4BackendCall(
            path=ast.path.strip(),
            packed_context=packed,
            intent=ast.intent,
            name=name,
            weight=weight,
        )

    def source_label(self, ast):
        return {"name": ast.name, "weight": ast.weight}

    def expanded_source(self, ast):
        return Url4ExpandedSource(inner=ast.inner)

    def expandable_atom(self, ast):
        return ast

    def binding(self, ast):
        sep = ast.sep
        kind = "=" if sep == "=" else ":"
        return Url4Binding(name=ast.name, value=ast.value, kind=kind)

    def eq_value(self, ast):
        return ast

    def atom_no_binding(self, ast):
        return ast

    def backend_context(self, ast):
        return ast

    def backend_path(self, ast):
        return ast

    def group(self, ast):
        elems = ast.elems if isinstance(ast.elems, list) else [ast.elems] if ast.elems else []
        nodes = [
            e
            for e in elems
            if isinstance(
                e,
                Url4Url
                | Url4RelUrl
                | Url4Text
                | Url4List
                | Url4BackendCall
                | Url4ExpandedSource
                | Url4Binding,
            )
        ]
        return Url4List(items=tuple(nodes))

    def context(self, ast):
        return ast

    def start(self, ast):
        return ast


# Compiled once at module import.
_parser = compile(GRAMMAR)


def parse(context: str) -> Url4Node:
    """Parse a url4 context string into a typed AST."""
    return _parser.parse(context.strip(), semantics=Url4Semantics())


__all__ = ["GRAMMAR", "Url4Semantics", "parse"]
