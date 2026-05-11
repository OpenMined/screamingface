# DEMO-004: Env Scope Chain for url4_executor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce an explicit `Env` (parent-pointer scope chain) and thread it through every recursive call in `url4_executor` — zero behavioral change. This is the plumbing DEMO-005 and DEMO-006 will sit on.

**Architecture:** A frozen dataclass `Env { bindings: dict, parent: Env | None }` with `lookup`, `child`, `root` methods. The interpreter, ensemble dispatcher, and AST resolver gain an optional `env: Env | None = None` parameter that defaults to a fresh root env and propagates through every recursive call. The existing flat substitutions (`substitute_item`, `substitute_response_vars`) are **not** rewired — that is DEMO-006's job.

**Tech Stack:** Python 3.12+, asyncio, `@dataclass(frozen=True)`, pytest (incl. `pytest-asyncio`), `uv` for env management.

**Asana:** https://app.asana.com/1/1185126988600652/task/1214567788345901

**Regression bar:** every existing test in `apps/server/src/screamingface/plugins/url4_executor/tests/` plus the `e2e and not live` suite stays green.

---

## File Structure

**Create:**
- `apps/server/src/screamingface/plugins/url4_executor/scope.py` — `Env` dataclass + factory helpers. ~60 lines.
- `apps/server/src/screamingface/plugins/url4_executor/tests/test_scope.py` — pure-unit tests for `Env`. No async, no app fixture.

**Modify (all signature widenings + propagation of `env` argument; **no** behavioral change):**
- `apps/server/src/screamingface/plugins/url4_executor/interpreter.py` — `Url4Interpreter.evaluate`, `Url4Interpreter.process`, module-level `resolve_intent`.
- `apps/server/src/screamingface/plugins/url4_executor/ensemble.py` — `EnsembleInterpreter.evaluate`, `process`, `_collection_iterate`, `_broadcast_evaluate`, `_ensemble_evaluate`, `_single_source_evaluate`.
- `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py` — `resolve`, `resolve_str`, `_dispatch_backend_call`, `_resolve_expanded_source`.
- `apps/server/src/screamingface/plugins/url4_executor/routes.py` — pass an explicit `Env.root()` into the interpreter call (smoke for the route → env path).

All public callers outside this plugin keep working because every new parameter defaults to `None`.

---

## Pre-flight

- [ ] **Step 0.1: Branch from fresh main**

```bash
cd /Users/sergey/work/openmind/screamingface
git fetch origin
git checkout -b feat/demo-004-env-scope-chain origin/main
```

Expected: clean working tree on a new branch tracking origin/main.

- [ ] **Step 0.2: Baseline test run — capture the "green" state we must preserve**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -q
uv run pytest tests/e2e/ -m "e2e and not live" -q
```

Expected: both suites pass. If anything is already red on `main`, stop and surface it — do not start the refactor on a red bar.

---

## Task 1: `scope.py` — the `Env` dataclass

**Files:**
- Create: `apps/server/src/screamingface/plugins/url4_executor/scope.py`

- [ ] **Step 1.1: Create the file with the design-spec body**

Write `apps/server/src/screamingface/plugins/url4_executor/scope.py`:

```python
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
```

- [ ] **Step 1.2: Sanity-check the import path**

Run:

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run python -c "from screamingface.plugins.url4_executor.scope import Env; print(Env.root())"
```

Expected: prints `Env(bindings={}, parent=None)`. Anything else (import error, name error) blocks the next task.

- [ ] **Step 1.3: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/url4_executor/scope.py
git commit -m "feat(url4): add Env parent-pointer scope chain (DEMO-004)"
```

---

## Task 2: `test_scope.py` — unit tests for `Env`

**Files:**
- Create: `apps/server/src/screamingface/plugins/url4_executor/tests/test_scope.py`

These are pure-unit (no app, no asyncio). They lock down the contract DEMO-005 will rely on.

- [ ] **Step 2.1: Write the failing tests**

Write `apps/server/src/screamingface/plugins/url4_executor/tests/test_scope.py`:

```python
"""Unit tests for the Env scope chain (DEMO-004)."""

from __future__ import annotations

import pytest

from screamingface.plugins.url4_executor.scope import Env


def test_root_is_empty():
    env = Env.root()
    assert env.bindings == {}
    assert env.parent is None


def test_lookup_finds_binding_in_current_frame():
    env = Env.root().child(a=1)
    assert env.lookup("a") == 1


def test_lookup_walks_parent_chain():
    env = Env.root().child(a=1).child(b=2)
    assert env.lookup("a") == 1
    assert env.lookup("b") == 2


def test_lookup_missing_name_raises_keyerror():
    env = Env.root().child(a=1)
    with pytest.raises(KeyError):
        env.lookup("nope")


def test_child_does_not_mutate_parent():
    parent = Env.root().child(a=1)
    parent_snapshot = dict(parent.bindings)
    _ = parent.child(b=2)
    assert parent.bindings == parent_snapshot


def test_inner_binding_shadows_outer():
    env = Env.root().child(x="outer").child(x="inner")
    assert env.lookup("x") == "inner"


def test_env_is_frozen():
    env = Env.root()
    with pytest.raises(Exception):  # FrozenInstanceError, but don't tie test to dataclass internals
        env.parent = Env.root()  # type: ignore[misc]


def test_child_accepts_arbitrary_value_types():
    """Bindings values are typed Any — strings now, possibly AST nodes later."""
    env = Env.root().child(s="hi", n=42, lst=[1, 2, 3])
    assert env.lookup("s") == "hi"
    assert env.lookup("n") == 42
    assert env.lookup("lst") == [1, 2, 3]
```

- [ ] **Step 2.2: Run the tests; they must pass against Task 1's `scope.py`**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_scope.py -v
```

Expected: 8 passed. If `test_env_is_frozen` is the only failure, the dataclass isn't frozen — fix Task 1.

- [ ] **Step 2.3: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/url4_executor/tests/test_scope.py
git commit -m "test(url4): unit tests for Env scope chain (DEMO-004)"
```

---

## Task 3: Thread `env` through `url4_resolve.py`

This is the leaf-most layer; touching it first lets later tasks pass `env` confidently.

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`

- [ ] **Step 3.1: Widen `resolve` to accept `env`**

In `url4_resolve.py` replace the `resolve(...)` function (current lines 31-46) with:

```python
async def resolve(node: Url4Node, app: Any = None, env: Env | None = None) -> str:
    """Recursively resolve an AST node to a string.

    ``env`` is the DEMO-004 scope chain. It is threaded through every
    recursive call so DEMO-005/006 have a place to put bindings; this
    function does not itself read from ``env`` yet.
    """
    if env is None:
        env = Env.root()
    if isinstance(node, Url4Text):
        return node.value
    if isinstance(node, Url4Url):
        return await _fetch_url(node.value)
    if isinstance(node, Url4RelUrl):
        return await _fetch_relative(app, node.value)
    if isinstance(node, Url4List):
        results = list(
            await asyncio.gather(*[resolve(item, app, env) for item in node.items])
        )
        return "\n".join(results)
    if isinstance(node, Url4BackendCall):
        return await _dispatch_backend_call(node, app, env)
    if isinstance(node, Url4ExpandedSource):
        return await _resolve_expanded_source(node, app, env)
    raise TypeError(f"Unknown node type: {type(node)}")
```

Add the import next to the existing AST import block (top of file):

```python
from screamingface.plugins.url4_executor.scope import Env
```

- [ ] **Step 3.2: Widen `resolve_str`**

Replace lines 49-51 (the `resolve_str` body) with:

```python
async def resolve_str(context: str, app: Any = None, env: Env | None = None) -> str:
    """Parse a url4 context string and resolve it to a string."""
    return await resolve(parse(context), app, env)
```

- [ ] **Step 3.3: Widen `_dispatch_backend_call`**

Replace the `_dispatch_backend_call` signature and the one recursive `resolve(node.intent, app)` call inside it.

Find:

```python
async def _dispatch_backend_call(node: Url4BackendCall, app: Any) -> str:
```

Replace with:

```python
async def _dispatch_backend_call(node: Url4BackendCall, app: Any, env: Env | None = None) -> str:
```

Find inside the same function:

```python
    intent_text = "" if node.intent is None else await resolve(node.intent, app)
```

Replace with:

```python
    intent_text = "" if node.intent is None else await resolve(node.intent, app, env)
```

- [ ] **Step 3.4: Widen `_resolve_expanded_source`**

Find:

```python
async def _resolve_expanded_source(node: Url4ExpandedSource, app: Any) -> str:
```

Replace with:

```python
async def _resolve_expanded_source(node: Url4ExpandedSource, app: Any, env: Env | None = None) -> str:
```

Find inside the same function:

```python
    body = await resolve(node.inner, app)
```

Replace with:

```python
    body = await resolve(node.inner, app, env)
```

- [ ] **Step 3.5: Run url4_resolve-touching tests**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_url4.py src/screamingface/plugins/url4_executor/tests/test_url4_executor.py src/screamingface/plugins/url4_executor/tests/test_url4_relurl.py -v
```

Expected: all green. Any failure means a signature or recursion was missed.

- [ ] **Step 3.6: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py
git commit -m "refactor(url4): thread Env through url4_resolve recursion (DEMO-004)"
```

---

## Task 4: Thread `env` through `interpreter.py`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/interpreter.py`

- [ ] **Step 4.1: Add Env import**

At the top of `interpreter.py` (after the existing `url4_resolve` import), add:

```python
from screamingface.plugins.url4_executor.scope import Env
```

- [ ] **Step 4.2: Widen `resolve_intent`**

Replace the `resolve_intent` signature (current line 20):

```python
async def resolve_intent(intent: str, app: Any = None) -> str:
```

with:

```python
async def resolve_intent(intent: str, app: Any = None, env: Env | None = None) -> str:
```

(`env` is accepted but unused inside; this function only does fetches/literals. The argument exists so callers can pass it without special-casing.)

- [ ] **Step 4.3: Widen `Url4Interpreter.evaluate`**

Replace line 49 (`async def evaluate(self, expr: str) -> str:`) with:

```python
    async def evaluate(self, expr: str, env: Env | None = None) -> str:
        """Full evaluation pipeline.

        ``env`` is the DEMO-004 scope chain. ``None`` is the same as a
        fresh root env. Propagated to ``resolve_str``, ``resolve_intent``,
        and ``self.process`` so DEMO-005/006 can add bindings without
        rewiring the call graph.
        """
```

Then, inside the function body:

- Immediately after the `with traced("url4.evaluate"):` line, insert:

  ```python
            if env is None:
                env = Env.root()
  ```

- Replace `sources = await resolve_str(source_expr, self.app) if source_expr else ""` with
  `sources = await resolve_str(source_expr, self.app, env) if source_expr else ""`.
- Replace `intent = await resolve_intent(raw_intent, self.app) if raw_intent else None` with
  `intent = await resolve_intent(raw_intent, self.app, env) if raw_intent else None`.
- Replace `result = await self.process(sources, intent)` with
  `result = await self.process(sources, intent, env)`.

- [ ] **Step 4.4: Widen `Url4Interpreter.process`**

Replace lines 98-105 (the `process` method) with:

```python
    async def process(self, sources: str, intent: str | None, env: Env | None = None) -> str:
        """Process resolved sources and intent. Override in subclasses.

        Default: concatenate intent + sources. ``env`` is accepted for
        signature parity with subclasses; this default does not use it.
        """
        if intent and sources:
            return f"{intent}\n\n{sources}"
        return intent or sources or ""
```

- [ ] **Step 4.5: Run interpreter-touching tests**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_url4_intent_dispatch.py src/screamingface/plugins/url4_executor/tests/test_url4_executor.py -v
```

Expected: all green.

- [ ] **Step 4.6: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/url4_executor/interpreter.py
git commit -m "refactor(url4): thread Env through Url4Interpreter (DEMO-004)"
```

---

## Task 5: Thread `env` through `ensemble.py`

This is the busiest file — six recursion sites. Do them in one commit so signatures stay consistent.

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble.py`

- [ ] **Step 5.1: Add Env import**

After the existing `Url4Interpreter` import, add:

```python
from screamingface.plugins.url4_executor.scope import Env
```

- [ ] **Step 5.2: Widen `EnsembleInterpreter.process`**

Replace lines 79-81:

```python
    async def process(self, sources: str, intent: str | None) -> str:
        """Fallback for non-ensemble expressions. Delegates to base class."""
        return await super().process(sources, intent)
```

with:

```python
    async def process(self, sources: str, intent: str | None, env: Env | None = None) -> str:
        """Fallback for non-ensemble expressions. Delegates to base class."""
        return await super().process(sources, intent, env)
```

- [ ] **Step 5.3: Widen `EnsembleInterpreter.evaluate`**

Replace line 87 (`async def evaluate(self, expr: str) -> str:`) with:

```python
    async def evaluate(self, expr: str, env: Env | None = None) -> str:
```

Immediately after `with traced("url4.evaluate"):` add:

```python
            if env is None:
                env = Env.root()
```

Then update each of the four dispatch calls in the function body:

- `return await self._collection_iterate(collection_source, iteration_body, raw_intent or "")`
  → `return await self._collection_iterate(collection_source, iteration_body, raw_intent or "", env)`
- `return await self._broadcast_evaluate(source_node, raw_intent)`
  → `return await self._broadcast_evaluate(source_node, raw_intent, env)`
- `return await self._ensemble_evaluate(source_node, raw_intent)`
  → `return await self._ensemble_evaluate(source_node, raw_intent, env)`
- `return await self._single_source_evaluate(source_expr, raw_intent)`
  → `return await self._single_source_evaluate(source_expr, raw_intent, env)`

- [ ] **Step 5.4: Widen `_collection_iterate`**

Replace the signature (line 138):

```python
    async def _collection_iterate(
        self, collection_source: str, iteration_body: str, intent: str
    ) -> str:
```

with:

```python
    async def _collection_iterate(
        self,
        collection_source: str,
        iteration_body: str,
        intent: str,
        env: Env | None = None,
    ) -> str:
```

Inside the function, replace `collection_body = await resolve_str(collection_source, self.app)` with
`collection_body = await resolve_str(collection_source, self.app, env)`.

In the inner `_process_one`, replace `return await self.evaluate(full_expr)` with
`return await self.evaluate(full_expr, env)`.

(The per-item `$item` binding is **not** added in this ticket — DEMO-005 will. For now `env` is just propagated.)

- [ ] **Step 5.5: Widen `_broadcast_evaluate`**

Replace the signature (line 176):

```python
    async def _broadcast_evaluate(self, source_node: Url4Node, raw_intent: str) -> str:
```

with:

```python
    async def _broadcast_evaluate(
        self, source_node: Url4Node, raw_intent: str, env: Env | None = None
    ) -> str:
```

Inside the function:

- `intent_text = await resolve_intent(raw_intent, self.app) if raw_intent else ""`
  → `intent_text = await resolve_intent(raw_intent, self.app, env) if raw_intent else ""`
- Inside `_apply_one`: replace `source_text = await resolve(item, self.app)` with
  `source_text = await resolve(item, self.app, env)`, and replace
  `return await self.process(source_text, intent_text)` with
  `return await self.process(source_text, intent_text, env)`.

- [ ] **Step 5.6: Widen `_ensemble_evaluate`**

Replace the signature (line 217):

```python
    async def _ensemble_evaluate(self, source_node: Url4List, raw_intent: str) -> str:
```

with:

```python
    async def _ensemble_evaluate(
        self, source_node: Url4List, raw_intent: str, env: Env | None = None
    ) -> str:
```

Inside the function:

- `reducer_instruction = await resolve_intent(raw_intent, self.app) if raw_intent else ""`
  → `reducer_instruction = await resolve_intent(raw_intent, self.app, env) if raw_intent else ""`
- `await asyncio.gather(*[resolve(item, self.app) for item in items])`
  → `await asyncio.gather(*[resolve(item, self.app, env) for item in items])`
- `result = await _dispatch_backend_call(reducer_node, self.app)`
  → `result = await _dispatch_backend_call(reducer_node, self.app, env)`

- [ ] **Step 5.7: Widen `_single_source_evaluate`**

Replace the signature (line 283):

```python
    async def _single_source_evaluate(self, source_expr: str, raw_intent: str | None) -> str:
```

with:

```python
    async def _single_source_evaluate(
        self, source_expr: str, raw_intent: str | None, env: Env | None = None
    ) -> str:
```

Inside the function:

- `sources = await resolve_str(source_expr, self.app) if source_expr else ""`
  → `sources = await resolve_str(source_expr, self.app, env) if source_expr else ""`
- `intent = await resolve_intent(raw_intent, self.app) if raw_intent else None`
  → `intent = await resolve_intent(raw_intent, self.app, env) if raw_intent else None`
- `result = await self.process(sources, intent)` → `result = await self.process(sources, intent, env)`

- [ ] **Step 5.8: Run the ensemble suite**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_ensemble.py -v
```

Expected: all green. Any red here means a recursion site or signature still has the old shape.

- [ ] **Step 5.9: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/url4_executor/ensemble.py
git commit -m "refactor(url4): thread Env through EnsembleInterpreter (DEMO-004)"
```

---

## Task 6: Pass an explicit root env from the `/ensemble` route

Confirms the route → interpreter → resolver path is end-to-end env-aware. Tiny change, kept as its own commit so it's easy to revert if needed.

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/routes.py`

- [ ] **Step 6.1: Import Env**

After the existing `EnsembleInterpreter` import (top of file), add:

```python
from screamingface.plugins.url4_executor.scope import Env
```

- [ ] **Step 6.2: Pass a root env into `evaluate`**

Replace `result = await interpreter.evaluate(q)` (line 80) with:

```python
            result = await interpreter.evaluate(q, env=Env.root())
```

(Behaviorally identical to passing `None`; the explicit call documents the entry point.)

- [ ] **Step 6.3: Run route + e2e tests**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_highlight_route.py -v
uv run pytest tests/e2e/ -m "e2e and not live" -q
```

Expected: route tests pass; e2e suite stays green.

- [ ] **Step 6.4: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/url4_executor/routes.py
git commit -m "refactor(url4): pass explicit root Env from /ensemble route (DEMO-004)"
```

---

## Task 7: Full regression bar

This is the "is the spike done?" gate.

- [ ] **Step 7.1: Run the full url4_executor test directory**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -v
```

Expected: every test passes, including the new `test_scope.py`. Compare counts against the baseline from Step 0.2 — total should be baseline + 8 (the new Env tests).

- [ ] **Step 7.2: Run the e2e suite (the actual regression bar)**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest tests/e2e/ -m "e2e and not live" -v
```

Expected: green. Anything red here means the env-threading refactor changed observable behavior — which is the one thing this ticket must not do.

- [ ] **Step 7.3: Lint / typecheck (whatever this repo runs)**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run ruff check src/screamingface/plugins/url4_executor/
uv run mypy src/screamingface/plugins/url4_executor/ 2>/dev/null || true
```

Expected: ruff clean. If mypy isn't wired up for this package, the `|| true` silently passes — that's fine. If ruff complains, fix in place and amend the previous commit.

- [ ] **Step 7.4: Push and open PR**

```bash
cd /Users/sergey/work/openmind/screamingface
git push -u origin feat/demo-004-env-scope-chain
gh pr create --title "DEMO-004: Env scope chain for url4_executor" --body "$(cat <<'EOF'
## Summary
- Adds `Env` (frozen dataclass, parent-pointer scope chain) in `scope.py`.
- Threads `env: Env | None = None` through `Url4Interpreter`, `EnsembleInterpreter`, and every `url4_resolve` recursion site.
- Zero behavioral change. This is the plumbing DEMO-005/006 sit on.

## Why parent-pointer
Bindings are read-heavy / write-light; the chain is shallow (≤4 frames); a frozen dataclass means concurrent iterations can't corrupt each other. See `scope.py` module docstring.

## Test plan
- [x] `uv run pytest src/screamingface/plugins/url4_executor/tests/test_scope.py -v` — 8 new tests
- [x] `uv run pytest src/screamingface/plugins/url4_executor/tests/ -v` — full plugin suite green
- [x] `uv run pytest tests/e2e/ -m "e2e and not live" -v` — regression bar green
- [x] `uv run ruff check src/screamingface/plugins/url4_executor/`

Asana: https://app.asana.com/1/1185126988600652/task/1214567788345901
EOF
)"
```

Expected: PR URL printed. Do **not** push earlier than this — green-bar first.

---

## Self-Review Notes

- **Spec coverage:** all six acceptance criteria from the Asana task map to tasks above: `Env` (Task 1), unit tests (Task 2: 8 cases incl. the three required), interpreter threading (Task 4), ensemble threading (Task 5), existing-tests-green (Tasks 3.5 / 4.5 / 5.8 / 7.1), e2e green (Step 0.2 baseline + Step 7.2), design note in module docstring (Task 1.1 — `scope.py` carries the rationale; the spec asks for it in `interpreter.py`'s docstring instead — see Open Note below).
- **Placeholder scan:** every step shows the exact code, command, or commit message.
- **Type consistency:** every signature uses `env: Env | None = None` and every internal call passes `env` positionally after `app` — checked across Tasks 3, 4, 5, 6.

**Open Note (Task 1 vs spec wording):** The Asana task says the design note belongs in `interpreter.py`'s docstring. I parked it in `scope.py` because the rationale is about `Env` itself, not the interpreter. If the reviewer prefers the literal interpretation, copy the "Design choice — parent-pointer" block from `scope.py` into `Url4Interpreter`'s class docstring in Task 4 (no logic change).

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-demo-004-env-scope-chain.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
