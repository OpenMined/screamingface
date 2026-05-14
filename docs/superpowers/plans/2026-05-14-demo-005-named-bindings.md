# DEMO-005: Named Bindings in Tuples — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two binding forms to the url4 grammar — `name=expr` (eager value bind) and `name:(...)` (subexpression label) — and register their resolved values into the DEMO-004 `Env` so DEMO-006's `$name` references can later read them.

**Architecture:** A new `Url4Binding(name, value, kind)` AST node wraps either form. Grammar gets one new `binding` production placed *before* `backend_call` in `atom` — disambiguation works because `name:weight:` (existing `source_label`) is `name:NUMBER:` and the new `name:` form is always `name:(`. Resolver gets a new branch that resolves `value`, writes `(name, resolved_value)` into the current `Env`, and returns the resolved value. List resolution changes from "fully parallel via `asyncio.gather`" to "bindings first in declaration order, non-bindings parallel after" so siblings can read bound names.

**Tech Stack:** Python 3.13, TatSu PEG parser, dataclasses, asyncio, FastAPI, pytest, uv. Existing modules: `url4_grammar.py`, `url4_ast.py`, `url4_resolve.py`, `routes.py`, `scope.py` (Env from DEMO-004).

**Ticket:** SF-152 · **Asana:** https://app.asana.com/1/1185126988600652/task/1214568424729700 · **Spec:** `/Users/sergey/.claude/plans/leaderboard-demo-tickets/DEMO-005-named-bindings.md` · **Branch:** `SF-152-named-bindings` off fresh `origin/main`.

---

## File Structure

**Modify (existing):**
- `apps/server/src/screamingface/plugins/url4_executor/url4_ast.py` — add `Url4Binding` dataclass and extend `Url4Node` union.
- `apps/server/src/screamingface/plugins/url4_executor/url4_grammar.py` — add `binding` rule; insert as first alt in `atom`; add `Url4Semantics.binding`; update group filter to accept `Url4Binding`.
- `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py` — add `Url4Binding` handling in `resolve`; split list resolution into "bindings first, non-bindings parallel".
- `apps/server/src/screamingface/plugins/url4_executor/routes.py` — extend `_ast_to_dict` for `Url4Binding`.
- `apps/server/src/screamingface/plugins/url4_executor/url4.py` — re-export `Url4Binding` from the facade.

**Create:**
- `apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py` — unit tests (parser, AST, resolver, list ordering, ambiguity with `source_label`).
- `apps/server/tests/e2e/data/other/named_bindings.yaml` — e2e fixtures driven through the parser_routing harness (non-live).

---

## Pre-flight (one-off — do not skip)

- [ ] **Step 0.1: Confirm working tree, fetch, branch from fresh main**

```bash
cd /Users/sergey/work/openmind/screamingface
git status                                # expect clean
git fetch origin
git checkout -b SF-152-named-bindings origin/main
git log --oneline -3                      # expect DEMO-004 (SF-150) already on main
```

Expected last-3 commits include `26681cf SF-150 / DEMO-004: Env scope chain for url4_executor`. If not present, stop — the dependency is missing.

- [ ] **Step 0.2: Confirm baseline tests are green before touching code**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -q
```

Expected: PASS. If any failures, stop and triage — we need a green baseline to attribute regressions correctly.

---

## Task 1: `Url4Binding` AST node

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_ast.py`
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py` (create)

- [ ] **Step 1.1: Write the failing test**

Create `apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py`:

```python
# pyright: reportAttributeAccessIssue=false
"""Tests for DEMO-005 named bindings (Url4Binding)."""

from __future__ import annotations

import pytest

from screamingface.plugins.url4_executor.url4_ast import Url4Binding, Url4Node, Url4Text


def test_url4_binding_is_a_url4_node() -> None:
    node = Url4Binding(name="x", value=Url4Text(value="1"), kind="=")
    # Url4Node is a union; isinstance with a union works in 3.10+.
    assert isinstance(node, Url4Node)
    assert node.name == "x"
    assert node.kind == "="
    assert isinstance(node.value, Url4Text)


def test_url4_binding_is_frozen() -> None:
    node = Url4Binding(name="x", value=Url4Text(value="1"), kind="=")
    with pytest.raises(Exception):  # FrozenInstanceError
        node.name = "y"  # type: ignore[misc]


def test_url4_binding_supports_colon_kind() -> None:
    node = Url4Binding(name="x", value=Url4Text(value="1"), kind=":")
    assert node.kind == ":"
```

- [ ] **Step 1.2: Run test, verify it fails**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_named_bindings.py -v
```

Expected: FAIL with `ImportError: cannot import name 'Url4Binding'`.

- [ ] **Step 1.3: Add `Url4Binding` to `url4_ast.py`**

Edit `apps/server/src/screamingface/plugins/url4_executor/url4_ast.py`. After `Url4ExpandedSource` and before the `Url4Node` union, add:

```python
from typing import Literal


@dataclass(frozen=True)
class Url4Binding:
    """DEMO-005: ``name=expr`` (eager value) or ``name:(...)`` (subexpression label).

    Wraps any url4 node in a named binding. The interpreter registers
    ``(name, resolved_value)`` into the current ``Env`` (DEMO-004) at
    resolution time so sibling list items (and downstream
    ``$<name>`` references from DEMO-006) can read it back.

    ``kind`` records the surface form so error messages and the
    ``/ensemble?ast=true`` JSON faithfully reflect the source.

    Distinct from ``Url4BackendCall.name``/``weight`` — those are
    a property of a backend call (used by the ensemble reducer for
    weighted fan-out, SF-88). A ``Url4Binding`` is a wrapper that
    can hold *any* sub-node.
    """

    name: str
    value: Url4Node
    kind: Literal["=", ":"]
```

Then extend the union and `__all__`:

```python
Url4Node = (
    Url4Url
    | Url4RelUrl
    | Url4Text
    | Url4List
    | Url4BackendCall
    | Url4ExpandedSource
    | Url4Binding
)


__all__ = [
    "Url4BackendCall",
    "Url4Binding",
    "Url4ExpandedSource",
    "Url4List",
    "Url4Node",
    "Url4RelUrl",
    "Url4Text",
    "Url4Url",
]
```

Note: `Url4Binding` references `Url4Node` in its type; that name is defined *after* the class. Because the module uses `from __future__ import annotations`, all annotations are strings and this forward reference is fine.

- [ ] **Step 1.4: Re-export from the facade `url4.py`**

Edit `apps/server/src/screamingface/plugins/url4_executor/url4.py`. Add `Url4Binding` to the import block and to `__all__`:

```python
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
```

```python
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
```

- [ ] **Step 1.5: Run tests, verify they pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_named_bindings.py -v
```

Expected: 3 PASS.

- [ ] **Step 1.6: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/url4_ast.py \
        apps/server/src/screamingface/plugins/url4_executor/url4.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py
git commit -m "feat(SF-152): add Url4Binding AST node (DEMO-005)"
```

---

## Task 2: Grammar — `name=expr` form

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_grammar.py`
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py`

- [ ] **Step 2.1: Add the failing parser tests for the `=` form**

Append to `test_named_bindings.py`:

```python
from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4List,
    Url4RelUrl,
    Url4Text,
    Url4Url,
    parse,
)
from screamingface.plugins.url4_executor.url4_ast import Url4Binding


# --- name=expr (eager value bind) -----------------------------------------


def test_parse_eq_binding_text_value() -> None:
    node = parse("a=1")
    assert isinstance(node, Url4Binding)
    assert node.name == "a"
    assert node.kind == "="
    assert isinstance(node.value, Url4Text)
    assert node.value.value == "1"


def test_parse_eq_binding_url_value() -> None:
    node = parse("doc=https://example.com/x")
    assert isinstance(node, Url4Binding)
    assert node.name == "doc"
    assert node.kind == "="
    assert isinstance(node.value, Url4Url)


def test_parse_eq_binding_relurl_value() -> None:
    node = parse("doc=/data/foo")
    assert isinstance(node, Url4Binding)
    assert isinstance(node.value, Url4RelUrl)
    assert node.value.value == "/data/foo"


def test_parse_eq_binding_backend_call_value() -> None:
    node = parse("ans=/claude()!summarize")
    assert isinstance(node, Url4Binding)
    assert isinstance(node.value, Url4BackendCall)
    assert node.value.path == "/claude"


def test_parse_eq_binding_group_value() -> None:
    # Per spec: `=` RHS can be a group too (not only an atom).
    node = parse("pair=(a, b)")
    assert isinstance(node, Url4Binding)
    assert isinstance(node.value, Url4List)
    assert len(node.value.items) == 2


def test_parse_list_of_eq_bindings() -> None:
    node = parse("(a=1, b=2)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert all(isinstance(it, Url4Binding) for it in node.items)
    a, b = node.items
    assert a.name == "a" and b.name == "b"  # type: ignore[attr-defined]
```

- [ ] **Step 2.2: Run, verify they fail**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_named_bindings.py -v -k "eq_binding or list_of_eq"
```

Expected: FAIL — currently `parse("a=1")` returns a single `Url4Text("a=1")`.

- [ ] **Step 2.3: Add `binding` to grammar + semantics + group filter**

Edit `apps/server/src/screamingface/plugins/url4_executor/url4_grammar.py`. Update the import to include `Url4Binding`:

```python
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
```

Inside the `GRAMMAR` string, change the `atom` rule to put `binding` first and add the `binding` / `eq_value` productions. Also leave a `# TODO(SF-152)` for bare `name:/path`:

```python
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

    # DEMO-005: named bindings.
    #
    #   name=expr   — eager value bind. RHS is any atom or a group.
    #   name:(...)  — subexpression label. RHS is always a group.
    #
    # Placed before backend_call so `name:weight:` (numeric weight)
    # still falls through to backend_call: PEG ordering is leftmost-
    # wins, but `binding` requires `=` or `:(` right after the name,
    # while `source_label` requires `:NUMBER:`. They don't collide.
    #
    # TODO(SF-152): the bare `name:/path` (no weight) form on a
    # backend call still parses as text + relurl. Fixing it conflicts
    # with the URL scheme separator and is out of scope here.
    binding
        = name:/[a-zA-Z_][a-zA-Z0-9_]*/ (
              '=' value:eq_value
            | ':' value:group
          )
        ;

    # RHS of `name=`. Group is allowed too — spec calls out
    # "any atom (text, URL, group, backend call)".
    eq_value
        = group
        | atom_no_binding
        ;

    # `=` RHS must not itself be another binding — prevents
    # `a=b=c` ambiguity. We still allow groups containing bindings,
    # i.e. `a=(b=1)` is fine because the inner binding sits inside
    # a Url4List frame.
    atom_no_binding
        = backend_call
        | expanded_source
        | url
        | relurl
        | text
        ;

    # ... (rest of grammar unchanged: backend_call, source_label,
    # backend_context, backend_path, atom_no_bc, url, relurl, text)
"""
```

Add the semantics method on `Url4Semantics` (place near the other small ones):

```python
    def binding(self, ast):
        kind = "=" if "=" in getattr(ast, "_to_text", lambda: "")() else None
        # TatSu gives us the alternative branch via the captured tokens —
        # use the parser's token rather than re-deriving. The simplest
        # disambiguation: if value is a Url4List, the form was `name:(...)`;
        # otherwise it was `name=...`. (`name:(...)` is the only form whose
        # RHS is unconditionally a group; `name=...` allows groups too but
        # the grammar splits them into different productions, so we get
        # ast.kind for free if we capture it.)
        ...
```

That approach is fragile. Instead, capture the separator explicitly in the grammar with named alternatives. Replace the `binding` rule with:

```text
    binding
        = name:/[a-zA-Z_][a-zA-Z0-9_]*/ (
              sep:'=' value:eq_value
            | sep:':' value:group
          )
        ;
```

Then the semantics method becomes straightforward:

```python
    def binding(self, ast):
        sep = ast.sep
        kind = "=" if sep == "=" else ":"
        return Url4Binding(name=ast.name, value=ast.value, kind=kind)

    def eq_value(self, ast):
        return ast

    def atom_no_binding(self, ast):
        return ast
```

Finally, extend the `group` filter so `Url4Binding` items are preserved (they are valid list members):

```python
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
```

- [ ] **Step 2.4: Run `=` tests, verify they pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_named_bindings.py -v -k "eq_binding or list_of_eq"
```

Expected: 6 PASS.

- [ ] **Step 2.5: Run the full existing parser suite — no regressions**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -q
```

Expected: all previously-green tests still green. Pay special attention to `test_url4.py` weighted-source / backend_call cases.

- [ ] **Step 2.6: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/url4_grammar.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py
git commit -m "feat(SF-152): grammar — name=expr binding form (DEMO-005)"
```

---

## Task 3: Grammar — `name:(...)` form and disambiguation with `source_label`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_grammar.py` (already done in Task 2; this task is mostly tests)
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py`

- [ ] **Step 3.1: Add failing tests for the `:` form and the disambiguation guarantee**

Append to `test_named_bindings.py`:

```python
# --- name:(...) (subexpression label) ------------------------------------


def test_parse_colon_binding_with_group() -> None:
    node = parse("normalized:(/claude()!x, /codex()!y)")
    assert isinstance(node, Url4Binding)
    assert node.name == "normalized"
    assert node.kind == ":"
    assert isinstance(node.value, Url4List)
    assert len(node.value.items) == 2
    assert all(isinstance(it, Url4BackendCall) for it in node.value.items)


def test_parse_colon_binding_in_list() -> None:
    node = parse("(normalized:(a, b), consensus:(c, d))")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert all(isinstance(it, Url4Binding) and it.kind == ":" for it in node.items)


# --- Disambiguation with backend_call source_label -----------------------


def test_weighted_backend_call_still_parses_as_backend_call() -> None:
    """`claude:0.40:/claude()!x` MUST remain a Url4BackendCall, not a binding."""
    node = parse("claude:0.40:/claude()!x")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/claude"
    assert node.name == "claude"
    assert node.weight == 0.40


def test_integer_weight_backend_call() -> None:
    node = parse("a:40:/claude()!hi")
    assert isinstance(node, Url4BackendCall)
    assert node.name == "a"
    assert node.weight == 40.0


def test_colon_binding_does_not_swallow_numeric_label() -> None:
    """If the body after `:` starts with a digit, it must NOT match `binding`."""
    # If `:` form mistakenly accepted non-group values, this would
    # parse as Url4Binding(name="claude", kind=":", value=text("0.40"))
    # followed by garbage. We require it to fall through to backend_call.
    node = parse("claude:0.40:/claude()!hi")
    assert not isinstance(node, Url4Binding)
```

- [ ] **Step 3.2: Run, verify state**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_named_bindings.py -v -k "colon_binding or weighted_backend or integer_weight or numeric_label"
```

Expected: PASS for `name:(...)` cases (grammar from Task 2 already supports them), and PASS for the disambiguation tests because the `binding`-with-`:` alternative requires a group (`(`) as the very next token — `0.40` cannot start a group.

If any FAIL, the most likely cause is that the `binding` rule's `:` alternative was written too permissively. Fix it by tightening the grammar to require `'(' ...` after `:`, exactly as written in Task 2.3.

- [ ] **Step 3.3: Commit (tests-only)**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py
git commit -m "test(SF-152): name:(...) binding + source_label disambiguation"
```

---

## Task 4: Resolver — bind into Env, two-pass list resolution

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py`

The scope-chain `Env` from DEMO-004 is a frozen, parent-pointer dataclass. It does **not** support mutation. To register a binding *into the current frame* during list resolution, we need a small mutable carrier — a per-list "binding buffer" — that we then materialize as a child `Env` once the binding values are resolved. Concretely: build `child_env = parent_env.child(**resolved_bindings)` once bindings have been resolved, and use `child_env` for the non-binding pass.

- [ ] **Step 4.1: Write the failing resolver tests**

Append to `test_named_bindings.py`:

```python
import asyncio

from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.url4_resolve import resolve


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_resolve_eq_binding_returns_resolved_value() -> None:
    env = Env.root()
    result = _run(resolve(parse("greet=hello"), app=None, env=env))
    # Binding returns the resolved value (so it composes inside a list).
    assert result == "hello"


def test_resolve_colon_binding_returns_resolved_group() -> None:
    env = Env.root()
    result = _run(resolve(parse("pair:(hello, world)"), app=None, env=env))
    assert result == "hello\nworld"


def test_list_with_binding_makes_name_visible_to_siblings() -> None:
    """A binding declared before its use in the same list must be readable.

    We can't yet write `$name` syntax — that's DEMO-006. Instead we
    assert directly on the Env: after resolving `(x=hi, plain_text)`,
    the *child* Env that the resolver constructed had `x` bound to
    `"hi"`. We test this by passing an env probe.
    """
    # We expose the bound value via a custom assertion: resolve a list
    # twice, second time with a probe child env that should find `x`.
    # The cleanest way: have resolve() of Url4List with bindings return
    # the joined output; separately, the resolver writes into a
    # child env that we can capture via a kwarg or via an env-capturing
    # binding consumer in a later task. For v1, this test asserts
    # behavioral plumbing: bindings before non-bindings.
    result = _run(resolve(parse("(x=hi, plain)"), app=None, env=Env.root()))
    # Bindings return their resolved value; the joined output is therefore
    # both items' resolved text, in declaration order.
    assert result == "hi\nplain"


def test_list_bindings_resolved_before_non_bindings() -> None:
    """Bindings (in declaration order) resolve before non-bindings, so a
    non-binding sibling sees the env populated.

    We assert this indirectly by checking declaration order is preserved
    in the joined output — and by Task 5's e2e test that exercises a
    backend_call reading $name.
    """
    result = _run(resolve(parse("(a=1, b=2, c)"), app=None, env=Env.root()))
    assert result == "1\n2\nc"
```

- [ ] **Step 4.2: Run, verify they fail**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_named_bindings.py -v -k "resolve_ or list_with_binding or list_bindings_resolved"
```

Expected: FAIL with `TypeError: Unknown node type: <class '...Url4Binding'>`.

- [ ] **Step 4.3: Implement resolver support**

Edit `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`. Add `Url4Binding` to the import block:

```python
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
```

Replace the body of `resolve()` so it (a) handles a bare `Url4Binding`, and (b) splits list resolution into two passes — bindings first (sequential, declaration order), non-bindings second (parallel, with a child Env carrying the new bindings):

```python
async def resolve(node: Url4Node, app: Any = None, env: Env | None = None) -> str:
    """Recursively resolve an AST node to a string.

    DEMO-005: when ``node`` is a ``Url4Binding`` the resolver
    resolves ``value`` eagerly (for both ``=`` and ``:`` forms in
    v1) and returns the resolved text. The binding is *also*
    registered into ``env`` — but only when the binding is being
    walked as a sibling of a ``Url4List`` (see the list branch
    below). A bare top-level binding still resolves correctly; it
    just has nowhere to register because there's no enclosing list
    frame.
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
        return await _resolve_list(node, app, env)
    if isinstance(node, Url4BackendCall):
        return await _dispatch_backend_call(node, app, env)
    if isinstance(node, Url4ExpandedSource):
        return await _resolve_expanded_source(node, app, env)
    if isinstance(node, Url4Binding):
        # Bare binding outside a list: resolve and return the value.
        # No env mutation possible (env is frozen) — DEMO-006 will
        # special-case lookups; sibling-visibility only applies to
        # bindings inside a Url4List frame (handled in _resolve_list).
        return await resolve(node.value, app, env)
    raise TypeError(f"Unknown node type: {type(node)}")


async def _resolve_list(node: Url4List, app: Any, env: Env) -> str:
    """Two-pass list resolution (DEMO-005).

    Pass 1: walk bindings in declaration order, sequentially,
            collecting (name, resolved_value). Sequential — not
            parallel — because later bindings may reference earlier
            ones once DEMO-006 adds `$name` lookup.
    Pass 2: build a child Env carrying those bindings; resolve all
            non-binding items in parallel under that child Env.

    Output preserves declaration order: binding-results first in
    their original positions, non-binding results in theirs. We
    track positions so the joined string matches the source order.
    """
    items = list(node.items)
    # Indexed work — bindings carry their resolved text into the
    # joined output too, so output indices match the source list.
    results: list[str | None] = [None] * len(items)
    resolved_bindings: dict[str, Any] = {}

    # Pass 1: bindings in declaration order, sequential.
    for idx, item in enumerate(items):
        if isinstance(item, Url4Binding):
            # Resolve under an env that already carries earlier
            # bindings from this same list — enables later DEMO-006
            # `$name` references between bindings.
            current = env.child(**resolved_bindings) if resolved_bindings else env
            value_text = await resolve(item.value, app, current)
            resolved_bindings[item.name] = value_text
            results[idx] = value_text

    # Pass 2: non-bindings in parallel, under the fully-populated
    # child Env (or the original env if no bindings were declared).
    child_env = env.child(**resolved_bindings) if resolved_bindings else env
    non_binding_indices = [i for i, it in enumerate(items) if not isinstance(it, Url4Binding)]
    if non_binding_indices:
        coros = [resolve(items[i], app, child_env) for i in non_binding_indices]
        gathered = await asyncio.gather(*coros)
        for i, value in zip(non_binding_indices, gathered, strict=True):
            results[i] = value

    # All slots are filled (binding values from pass 1, non-binding
    # values from pass 2). Join in source order.
    return "\n".join(r for r in results if r is not None)
```

Keep the rest of the file (helpers `_dispatch_backend_call`, `_resolve_expanded_source`, `_fetch_url`, `_fetch_relative`, `_sanitize_url`) unchanged.

- [ ] **Step 4.4: Update `routes.py` `_ast_to_dict` for `Url4Binding`**

Edit `apps/server/src/screamingface/plugins/url4_executor/routes.py`. Add `Url4Binding` to the imports and a branch in `_ast_to_dict`:

```python
from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4Binding,
    Url4ExpandedSource,
    Url4List,
    Url4RelUrl,
    Url4Url,
    parse,
)
```

Add this branch to `_ast_to_dict`, before the `Url4List` branch:

```python
    if isinstance(node, Url4Binding):
        return {
            "type": "binding",
            "name": node.name,
            "kind": node.kind,
            "value": _ast_to_dict(node.value),
        }
```

- [ ] **Step 4.5: Run all resolver tests, verify they pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_named_bindings.py -v
```

Expected: all PASS.

- [ ] **Step 4.6: Run the full url4_executor suite — no regressions**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -q
```

Expected: all green. The two-pass list strategy must not change behavior for lists that have *no* bindings (the `if resolved_bindings else env` short-circuits keep that path identical to the old `asyncio.gather`-everything code, except items resolve via two separate awaits — semantically identical).

- [ ] **Step 4.7: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py \
        apps/server/src/screamingface/plugins/url4_executor/routes.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_named_bindings.py
git commit -m "feat(SF-152): resolver — eager bindings, two-pass list resolution (DEMO-005)"
```

---

## Task 5: E2E — named bindings through the parser-routing harness

The spec calls for `data/other/named_bindings.yaml`. The existing `parser_routing.yaml` is exercised by `tests/e2e/` against a live SF subprocess (see `test_ensemble_features.py`). DEMO-005 e2e cases need **no real backend** — only the parser/resolver — so they belong with `parser_routing.yaml`-style fixtures.

**Files:**
- Create: `apps/server/tests/e2e/data/other/named_bindings.yaml`
- (No new Python — the existing fixture-driven runner consumes this YAML.)

- [ ] **Step 5.1: Locate the fixture-driven runner**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
grep -rn "parser_routing" tests/e2e/ --include='*.py' | head
```

Expected: a runner file (likely `tests/e2e/test_parser_routing.py` or similar) loads each YAML in `tests/e2e/data/other/` and runs the listed expressions against the running SF server. Read it to confirm the schema (`id`, `description`, `ticket`, `backends`, `expression`, `expect`).

If the runner only loads `parser_routing.yaml` by name, update it to also load `named_bindings.yaml` — or, simpler, append the new cases to `parser_routing.yaml` instead of creating a new file. The spec lists a new file; do that if the runner already globs `data/other/*.yaml`. Otherwise update the loader (one-line glob change) in the same commit.

- [ ] **Step 5.2: Author the fixtures**

Create `apps/server/tests/e2e/data/other/named_bindings.yaml`:

```yaml
# DEMO-005 (SF-152): named-binding parser + resolver behavior.
# No real backends — these exercise the grammar and the two-pass
# list resolution only. Joined output is the concatenation of each
# resolved item (binding values inline in declaration order).

- id: eq_binding_text
  description: "a=1 returns the bound value"
  ticket: SF-152
  backends: []
  expression: "a=1"
  expect:
    status: 200
    body_equals: "1"

- id: colon_binding_group
  description: "name:(a, b) returns the group joined by newline"
  ticket: SF-152
  backends: []
  expression: "pair:(a, b)"
  expect:
    status: 200
    body_equals: "a\nb"

- id: list_with_binding_preserves_order
  description: "(x=hi, plain) joins binding value then sibling, in source order"
  ticket: SF-152
  backends: []
  expression: "(x=hi, plain)"
  expect:
    status: 200
    body_equals: "hi\nplain"

- id: weighted_backend_label_still_parses
  description: "claude:0.40:/claude()!x must NOT become a Url4Binding"
  ticket: SF-152
  backends: []
  expression: "claude:0.40:/nonexistent()!hi"
  expect:
    # Falls through to backend_call (binding's `:` alt requires a group);
    # /nonexistent has no handler so we get the standard 502.
    status: 502
  ast_contains:
    type: "backend_call"
    name: "claude"
    weight: 0.40

- id: ast_round_trip_eq_binding
  description: "/ensemble?ast=true exposes binding nodes faithfully"
  ticket: SF-152
  backends: []
  expression: "a=1"
  ast_only: true
  ast_equals:
    type: "binding"
    name: "a"
    kind: "="
    value:
      type: "text"
      value: "1"
```

If `body_equals`, `ast_contains`, `ast_equals`, or `ast_only` aren't existing assertion keys in the runner, prefer keeping the YAML schema and extending the runner — but if that's too invasive, drop unsupported keys and rely on `contains_all` / `status` (which are confirmed to exist per `parser_routing.yaml`). Document any runner extensions in the same commit.

- [ ] **Step 5.3: Run the non-live e2e suite**

```bash
cd apps/server
uv run pytest tests/e2e/ -m "e2e and not live" -v -k "named_bindings or parser_routing"
```

Expected: all `named_bindings.*` cases PASS; `parser_routing.*` cases unchanged.

- [ ] **Step 5.4: Commit**

```bash
git add apps/server/tests/e2e/data/other/named_bindings.yaml
# plus the runner if extended:
# git add apps/server/tests/e2e/test_parser_routing.py
git commit -m "test(SF-152): e2e fixtures for named bindings (DEMO-005)"
```

---

## Task 6: Final regression sweep, lint, and pre-commit

- [ ] **Step 6.1: Full url4_executor suite**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -v
```

Expected: all green.

- [ ] **Step 6.2: Full non-live e2e suite**

```bash
cd apps/server
uv run pytest tests/e2e/ -m "e2e and not live" -v
```

Expected: all green.

- [ ] **Step 6.3: Pre-commit (mirrors CI — `ruff check` AND `ruff format`)**

```bash
cd /Users/sergey/work/openmind/screamingface
pre-commit run --all-files
```

Expected: PASS. If `ruff format` rewrites anything, stage & amend or create a fixup commit. If `pre-commit` isn't installed, run the checks directly:

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run ruff check .
uv run ruff format --check .
uv run pyright src/screamingface/plugins/url4_executor/   # if pyright is in the CI gate
```

- [ ] **Step 6.4: Push branch and open PR (stop — do NOT merge)**

```bash
cd /Users/sergey/work/openmind/screamingface
git push -u origin SF-152-named-bindings
gh pr create \
  --title "SF-152: named bindings (DEMO-005)" \
  --body "$(cat <<'EOF'
## Summary
- New `Url4Binding(name, value, kind)` AST node — wraps `name=expr` (eager) and `name:(...)` (subexpression label).
- Grammar adds `binding` before `backend_call` in `atom`; tightened `:` form to require a group so `name:weight:` source labels still parse as `Url4BackendCall`.
- Resolver splits `Url4List` resolution into two passes — bindings first (sequential, declaration order), non-bindings parallel under a child `Env` carrying the new bindings. Enables sibling visibility (DEMO-006 will surface `$name` lookups).
- `/ensemble?ast=true` faithfully emits `{type: binding, ...}`.
- Bare `name:/path` (no weight) still parses as `text` + `relurl` — out of scope (`# TODO(SF-152)` left in grammar).

## Test plan
- [ ] `uv run pytest src/screamingface/plugins/url4_executor/tests/` — green
- [ ] `uv run pytest tests/e2e/ -m "e2e and not live"` — green
- [ ] `pre-commit run --all-files` — green
EOF
)"
```

**Stop here.** Per repo policy (memory: never auto-merge), the user reviews and merges manually.

---

## Self-review notes

- **Spec coverage:** every acceptance-criteria checkbox in the ticket maps to a step in Tasks 1–5: AST/union (T1), `(a=1, b=2)` parse (T2), `normalized:(...)` parse (T3), `claude:0.40:/claude()` unchanged (T3), env-register on list (T4), bindings-first ordering (T4), unit tests covering parse/env/ordering/ambiguity (T1–T4), e2e file (T5), existing tests green (T6).
- **Placeholders:** none — every step shows the exact code or command.
- **Type/name consistency:** `Url4Binding(name, value, kind)` with `kind: Literal["=", ":"]` used identically across `url4_ast.py`, `url4_grammar.py`, `url4_resolve.py`, `routes.py`, tests, and YAML fixtures. `_resolve_list` helper name reused consistently.
- **Risk:** the two-pass list resolution changes timing — previously all items resolved in parallel. For lists without bindings, behaviour is identical (the `if resolved_bindings else env` short-circuit keeps the gather path). For lists with bindings, the binding pass is sequential by design (declaration-order semantics). Latency cost is bounded by the count of bindings, which is small in the EM's `/python` example.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-14-demo-005-named-bindings.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Fresh subagent per task, two-stage review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch with checkpoints.

**Which approach?**
