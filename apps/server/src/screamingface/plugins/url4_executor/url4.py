"""url4 — recursive context resolution protocol (TatSu PEG parser).

A url4 context value is either:

- A plain string (returned as-is)
- An absolute URL (fetched via HTTP GET)
- A relative URL ``/path`` (fetched via in-process ASGI)
- A parenthesized list: ``(item1, item2, item3)``
- A backend call: ``[name:weight:]/path(context)!intent``
- An expanded source: ``*source``

This module is a backward-compat facade over the three split modules:

- :mod:`.url4_ast` — typed dataclass AST nodes
- :mod:`.url4_grammar` — TatSu grammar + ``parse()``
- :mod:`.url4_resolve` — async ``resolve()`` / ``resolve_str()`` and
  the HTTP / backend-dispatch helpers

New code should import directly from those modules. The names below
are re-exported for existing callers (tests, interpreter, ensemble).
"""

from __future__ import annotations

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
from screamingface.plugins.url4_executor.url4_grammar import GRAMMAR, Url4Semantics, parse
from screamingface.plugins.url4_executor.url4_resolve import resolve, resolve_str

__all__ = [
    "GRAMMAR",
    "Url4BackendCall",
    "Url4Binding",
    "Url4ExpandedSource",
    "Url4List",
    "Url4Node",
    "Url4RelUrl",
    "Url4Semantics",
    "Url4Text",
    "Url4Url",
    "parse",
    "resolve",
    "resolve_str",
]
