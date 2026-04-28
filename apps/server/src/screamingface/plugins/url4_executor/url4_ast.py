"""Typed AST dataclasses for the url4 grammar.

Each node corresponds to one production in the TatSu grammar (see
:mod:`.url4_grammar`). Resolution lives in :mod:`.url4_resolve`.

Pulled out of ``url4.py`` so consumers that only need the type names
don't pay the cost of importing TatSu / httpx.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Url4Url:
    value: str


@dataclass(frozen=True)
class Url4RelUrl:
    value: str


@dataclass(frozen=True)
class Url4Text:
    value: str


@dataclass(frozen=True)
class Url4List:
    items: tuple[Url4Node, ...]


@dataclass(frozen=True)
class Url4BackendCall:
    """A backend-invocation node: ``[name:weight:]path(context)!<intent>``.

    Distinct from a :class:`Url4RelUrl` (which is a URL fetch via
    in-process ASGI GET) — this dispatches into a plugin's
    ``handle_backend_call`` instead.

    ``packed_context`` is the raw text inside the parens (SF-89 context
    packing). Empty string or None means "no inline context."

    ``name`` and ``weight`` are optional labels from the
    ``name:weight:`` prefix (SF-88 named + weighted sources). When
    present, the ensemble reducer formats the response with the name
    and weight so the LLM can weight responses proportionally.
    """

    path: str
    packed_context: str | None = None
    intent: Url4Node | None = None
    name: str | None = None
    weight: float | None = None


@dataclass(frozen=True)
class Url4ExpandedSource:
    """SF-92: ``*source`` expands a collection into individual items.

    The executor fetches ``inner``, parses it as a collection (JSON
    array, JSONL, or CSV), and treats each item as a separate source.
    The expanded items replace this node in the AST during resolution.
    """

    inner: Url4Node


Url4Node = Url4Url | Url4RelUrl | Url4Text | Url4List | Url4BackendCall | Url4ExpandedSource


__all__ = [
    "Url4BackendCall",
    "Url4ExpandedSource",
    "Url4List",
    "Url4Node",
    "Url4RelUrl",
    "Url4Text",
    "Url4Url",
]
