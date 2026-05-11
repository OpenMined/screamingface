"""Parent-pointer scope chain for url4 binding resolution (DEMO-004).

This is the plumbing only. No interpreter logic actually puts bindings
into an Env yet — DEMO-005/006 will. The point of landing this first
is so DEMO-005/006 have a stable shape to build against.

Design choice — parent-pointer (not copy-on-write or dict-stacking)
=================================================================

- Bindings within an iteration body are *read* by many lookups but
  *created* at most a handful per iteration — write-light, read-heavy.
- The chain is already short (rarely deeper than 4 levels in practice:
  outer / iteration / fanout / reducer).
- ``frozen=True`` means we never mutate; ``child()`` always returns a
  new ``Env``, so concurrent iterations cannot corrupt each other.

The ``Any`` typing for binding values is intentional — at this stage
bindings hold strings (resolved text). DEMO-005 may extend to
AST-node bindings if eager evaluation proves wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Env:
    """A single frame in the url4 scope chain."""

    bindings: dict[str, Any] = field(default_factory=dict)
    parent: Env | None = None

    def lookup(self, name: str) -> Any:
        """Walk the parent chain. Raise ``KeyError`` if not found."""
        env: Env | None = self
        while env is not None:
            if name in env.bindings:
                return env.bindings[name]
            env = env.parent
        raise KeyError(name)

    def child(self, **bindings: Any) -> Env:
        """Return a child scope carrying ``bindings``; ``self`` is the parent."""
        return Env(bindings=dict(bindings), parent=self)

    @classmethod
    def root(cls) -> Env:
        """A fresh, empty root env. Use this where ``env`` would otherwise be ``None``."""
        return cls()


__all__ = ["Env"]
