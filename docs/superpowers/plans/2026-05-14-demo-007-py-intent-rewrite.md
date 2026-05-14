# DEMO-007: `.py` Intent Grammar Rewrite to `/python` Backend Call — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At parse time, rewrite any relative URL ending in `.py` into a `Url4BackendCall(path="/python", packed_context=<original>)` so the rest of the pipeline sees a normal backend call.

**Architecture:** Single-line semantic change in `Url4Semantics.relurl`: after building the path string, if it ends in `.py` return a `Url4BackendCall` instead of a `Url4RelUrl`. No new AST node, no resolver change, no consumer changes — highlight, AST inspector, resolver, and ensemble all behave correctly because they already handle `Url4BackendCall`. Absolute `https://...` URLs are intentionally untouched (remote scripts out of scope: sandbox/signing).

**Tech Stack:** TatSu PEG, Python dataclasses, pytest.

**Ticket:** SF-154 · **Asana:** https://app.asana.com/1/1185126988600652/task/1214568118232085 · **Spec:** `/Users/sergey/.claude/plans/leaderboard-demo-tickets/DEMO-007-py-intent-rewrite.md` · **Branch:** `SF-154-py-intent-rewrite` off `SF-152-named-bindings` (DEMO-005 base; DEMO-005 not yet on main).

---

## File Structure

**Modify:**
- `apps/server/src/screamingface/plugins/url4_executor/url4_grammar.py` — `Url4Semantics.relurl` checks for `.py` suffix and returns a `Url4BackendCall` instead of `Url4RelUrl`; module docstring notes the rewrite.

**Create:**
- `apps/server/src/screamingface/plugins/url4_executor/tests/test_python_intent_rewrite.py` — 8 unit tests covering source-position rewrite, intent-position rewrite, lists, non-`.py` regression, `.py` in middle of path (regression), bare `/x.py` rewrite, `_ast_to_dict` serialization, `https://` absolute URLs unchanged.

---

## Pre-flight

- [ ] **Step 0.1: Branch from DEMO-005 base**

```bash
cd /Users/sergey/work/openmind/screamingface
git fetch origin
git checkout -b SF-154-py-intent-rewrite origin/SF-152-named-bindings
```

- [ ] **Step 0.2: Baseline tests green**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -q
```

---

## Task 1: Tests + implementation

**Files:**
- Create: `apps/server/src/screamingface/plugins/url4_executor/tests/test_python_intent_rewrite.py`
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_grammar.py`

- [ ] **Step 1.1: Write the failing tests**

```python
# pyright: reportAttributeAccessIssue=false
"""Tests for DEMO-007 (SF-154): `.py` paths rewrite to `/python` backend calls."""

from __future__ import annotations

from screamingface.plugins.url4_executor.decoder import split_intent
from screamingface.plugins.url4_executor.routes import _ast_to_dict
from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4List,
    Url4RelUrl,
    parse,
)


def test_plain_py_path_rewrites_to_python_backend_call() -> None:
    node = parse("/data/check_correct.py")
    assert isinstance(node, Url4BackendCall)
    assert node.path == "/python"
    assert node.packed_context == "/data/check_correct.py"
    assert node.intent is None


def test_py_path_inside_list_rewrites() -> None:
    node = parse("(/foo, /bar.py)")
    assert isinstance(node, Url4List)
    foo, bar = node.items
    assert isinstance(foo, Url4RelUrl)
    assert isinstance(bar, Url4BackendCall)
    assert bar.packed_context == "/bar.py"


def test_py_path_as_intent_rewrites() -> None:
    source_expr, intent, _ = split_intent("(a, b)!/data/check_correct.py")
    intent_node = parse(intent)
    assert isinstance(intent_node, Url4BackendCall)
    assert intent_node.path == "/python"
    assert intent_node.packed_context == "/data/check_correct.py"


def test_non_py_relurl_unchanged() -> None:
    assert isinstance(parse("/something/not-py"), Url4RelUrl)


def test_py_in_middle_of_path_is_not_rewritten() -> None:
    node = parse("/foo.py/bar")
    assert isinstance(node, Url4RelUrl)


def test_root_py_path_rewrites() -> None:
    node = parse("/x.py")
    assert isinstance(node, Url4BackendCall)
    assert node.packed_context == "/x.py"


def test_ast_to_dict_serializes_rewritten_node() -> None:
    d = _ast_to_dict(parse("/data/x.py"))
    assert d == {"type": "backend_call", "path": "/python", "packed_context": "/data/x.py"}


def test_https_py_url_is_not_rewritten() -> None:
    from screamingface.plugins.url4_executor.url4 import Url4Url
    node = parse("https://example.com/x.py")
    assert isinstance(node, Url4Url)
```

- [ ] **Step 1.2: Run, verify failures**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_python_intent_rewrite.py -v
```

Expected: 5 FAIL (positive rewrite cases), 3 PASS (negative regressions already correct).

- [ ] **Step 1.3: Implement rewrite in `Url4Semantics.relurl`**

Replace the body of `Url4Semantics.relurl` in `url4_grammar.py`:

```python
    def relurl(self, ast):
        value = ast.value.strip()
        # DEMO-007 (SF-154): `.py`-suffixed paths desugar at parse time
        # into a /python backend call. Done parser-side so the rest of
        # the pipeline sees a normal Url4BackendCall with no special-
        # casing. Absolute https:// URLs are intentionally NOT rewritten
        # — remote scripts are out of scope (sandbox/signing).
        if value.endswith(".py"):
            return Url4BackendCall(
                path="/python",
                packed_context=value,
                intent=None,
                name=None,
                weight=None,
            )
        return Url4RelUrl(value=value)
```

Also extend the module docstring to note the rewrite.

- [ ] **Step 1.4: Tests pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_python_intent_rewrite.py -v
```

Expected: 8 PASS.

- [ ] **Step 1.5: Full url4_executor regression**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -q
```

Expected: all green. (Note: any earlier test that asserted `parse("/foo.py")` is a `Url4RelUrl` becomes a contract change — none exist in the current suite.)

- [ ] **Step 1.6: Full non-live e2e regression**

```bash
cd apps/server
uv run pytest tests/e2e/test_url4_matrix.py -m "e2e and not live" -q
```

Expected: all green.

- [ ] **Step 1.7: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/url4_grammar.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_python_intent_rewrite.py
git commit -m "feat(SF-154): rewrite .py paths to /python backend calls (DEMO-007)"
```

---

## Task 2: Pre-commit, push, open PR

- [ ] **Step 2.1: Pre-commit (ruff check + format + pyright)**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
pre-commit run --from-ref origin/main --to-ref HEAD
```

- [ ] **Step 2.2: Push and open PR (stop — do NOT merge)**

```bash
cd /Users/sergey/work/openmind/screamingface
git push -u origin SF-154-py-intent-rewrite
gh pr create \
  --base SF-152-named-bindings \
  --title "SF-154: rewrite .py paths to /python backend calls (DEMO-007)" \
  --body "..."
```

Stacked on PR #167; rebase to `main` once #167 merges.

---

## Self-review notes

- **Spec coverage:** all 7 acceptance-criteria checkboxes map to one of the 8 tests above; the grammar docstring update covers the last one.
- **Placeholders:** none.
- **Type/name consistency:** `Url4BackendCall(path="/python", packed_context=<value>, intent=None, name=None, weight=None)` used consistently in both spec and grammar change.
- **Risk:** behavior change for existing `.py` URL fetches via URL4 — but the spec calls out that none exist (the runner doesn't exist yet either). Documented in the grammar docstring.
