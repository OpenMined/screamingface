# DEMO-006: `$name` Reference Resolution + Multi-Level `$item.dotted` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `$<name>` tokens resolve through the DEMO-004 `Env` (writing introduced in DEMO-005) and extend `$item.foo.bar` to walk multi-segment JSON paths recursively.

**Architecture:** Two-helper change in `ensemble_helpers.py` — (1) `substitute_response_vars` gains an optional `env: Env | None` param and consults the env *first* for any `$<name>`, falling back to the existing flat-entry list, falling back to leaving the token literal; (2) `substitute_item` regex widens from one segment to `(?:\.NAME)+`, walking the parsed JSON dict recursively with graceful miss. `Url4Text` resolution gets a new env-aware substitution pass so text-position `$name` refs (not just inside reducer instructions) resolve too. Order is fixed: `$item.*` first, generic `$<name>` second.

**Tech Stack:** Python 3.13, pytest, FastAPI, existing `Env` (parent-pointer scope chain), regex, json.

**Ticket:** Suggested SF-149 (Asana task TBD — user assigns) · **Spec:** `/Users/sergey/.claude/plans/leaderboard-demo-tickets/DEMO-006-name-refs-and-dotted.md` · **Branch:** `SF-149-name-refs` off fresh `origin/main` (after DEMO-005 / SF-152 merges; until then, off `SF-152-named-bindings`).

---

## File Structure

**Modify (existing):**
- `apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py` — extend `substitute_response_vars(env=...)`; extend `substitute_item` to multi-segment dotted; add a new `substitute_env_vars(text, env)` helper for env-only `$name` substitution used by `Url4Text` resolution.
- `apps/server/src/screamingface/plugins/url4_executor/ensemble.py` — pass `env=current_env` into `substitute_response_vars` in `_ensemble_evaluate`.
- `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py` — `resolve(Url4Text)` runs `substitute_env_vars(node.value, env)` so text-position references resolve.
- `apps/server/tests/e2e/data/other/named_bindings.yaml` — add one e2e case that exercises a sibling reading a binding.

**Create:**
- `apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py` — unit tests for env hits/misses, multi-segment dotted hits/misses, ordering between `$item.*` and `$name`, `Url4Text` env-aware resolution.

---

## Pre-flight

- [ ] **Step 0.1: Branch off fresh main (or DEMO-005 if SF-152 unmerged)**

```bash
cd /Users/sergey/work/openmind/screamingface
git status                                # expect clean
git fetch origin
# If SF-152 (DEMO-005) is already on main, branch from main:
if git log --oneline origin/main | grep -q "SF-152"; then
  git checkout -b SF-149-name-refs origin/main
else
  # Otherwise, build on top of the DEMO-005 branch — the helpers it
  # added are required.
  git checkout -b SF-149-name-refs origin/SF-152-named-bindings
fi
git log --oneline -3
```

Expected: HEAD has DEMO-005 work reachable (either via main or via the SF-152 branch).

- [ ] **Step 0.2: Confirm baseline tests are green**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -q
```

Expected: PASS (209 tests if branching off SF-152, 190 if DEMO-005 isn't on the chosen base — adjust expectation accordingly).

---

## Task 1: `substitute_env_vars(text, env)` — env-only `$name` substitution

A small new helper used by `Url4Text` resolution. It walks all `$<name>` tokens in the text, consults `Env.lookup`, and leaves unknown names literal. Reused by `substitute_response_vars` for the env-first lookup pass.

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py`
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py` (create)

- [ ] **Step 1.1: Write the failing tests**

Create `apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py`:

```python
# pyright: reportAttributeAccessIssue=false
"""Tests for DEMO-006 (SF-149): $<name> resolution + multi-segment $item.dotted."""

from __future__ import annotations

import pytest

from screamingface.plugins.url4_executor.ensemble_helpers import (
    FanoutResponse,
    substitute_env_vars,
    substitute_item,
    substitute_response_vars,
)
from screamingface.plugins.url4_executor.scope import Env


# ---------------------------------------------------------------------------
# substitute_env_vars — env-only $name substitution
# ---------------------------------------------------------------------------


def test_env_vars_replaces_known_name() -> None:
    env = Env.root().child(consensus="the answer is 42")
    assert substitute_env_vars("reduce: $consensus", env) == "reduce: the answer is 42"


def test_env_vars_walks_parent_chain() -> None:
    env = Env.root().child(outer="hi").child(inner="lo")
    assert substitute_env_vars("$outer $inner", env) == "hi lo"


def test_env_vars_leaves_unknown_literal() -> None:
    env = Env.root().child(x="1")
    assert substitute_env_vars("$unknown $x", env) == "$unknown 1"


def test_env_vars_none_env_is_noop() -> None:
    assert substitute_env_vars("plain $x text", None) == "plain $x text"


def test_env_vars_empty_string_is_noop() -> None:
    assert substitute_env_vars("", Env.root().child(x="1")) == ""


def test_env_vars_only_matches_word_boundaries() -> None:
    """`$consensus` must not match inside `$consensus_thing`."""
    env = Env.root().child(consensus="X", consensus_thing="Y")
    # Both names are distinct identifiers; both should replace exactly.
    assert substitute_env_vars("$consensus $consensus_thing", env) == "X Y"


def test_env_vars_non_string_value_is_json_encoded() -> None:
    """Env values may be non-string (lists/dicts). Match substitute_item behaviour."""
    env = Env.root().child(nums=[1, 2, 3])
    assert substitute_env_vars("got $nums", env) == "got [1, 2, 3]"
```

- [ ] **Step 1.2: Run, verify they fail**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_name_refs.py -v -k "env_vars"
```

Expected: FAIL with `ImportError: cannot import name 'substitute_env_vars'`.

- [ ] **Step 1.3: Implement `substitute_env_vars`**

Edit `apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py`. Add an import for `Env` and the new helper. Place after the `substitute_response_vars` definition.

Add to imports at the top:

```python
from screamingface.plugins.url4_executor.scope import Env
```

Add the new helper:

```python
# Identifier pattern shared by both env- and entries-based `$name`
# substitution. Word-boundary `\b` on the right prevents `$consensus`
# from matching the prefix of `$consensus_thing`.
_NAME_REF_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)\b")


def substitute_env_vars(text: str, env: Env | None) -> str:
    """Replace every ``$<name>`` token in ``text`` with ``env.lookup(name)``.

    DEMO-006 (SF-149): the read side of DEMO-005 bindings. Walks every
    identifier-shaped ``$<name>`` token; if the binding exists in
    ``env`` (or any ancestor frame), substitutes the value. Unknown
    names are left literal — matches ``substitute_response_vars``
    behaviour so LLMs see surprising tokens as text, not errors.

    Non-string values are JSON-encoded (matches ``substitute_item``).
    """
    if not text or env is None:
        return text

    def _repl(match: re.Match) -> str:
        name = match.group(1)
        try:
            value = env.lookup(name)
        except KeyError:
            return match.group(0)
        return value if isinstance(value, str) else json.dumps(value)

    return _NAME_REF_RE.sub(_repl, text)
```

Also extend `__all__`:

```python
__all__ = [
    "FanoutResponse",
    "_ResponseEntry",
    "_build_reducer_input",
    "_split_collection_iteration",
    "_substitute_item",
    "_substitute_response_vars",
    "build_reducer_input",
    "split_collection_iteration",
    "substitute_env_vars",
    "substitute_item",
    "substitute_response_vars",
]
```

- [ ] **Step 1.4: Run env_vars tests, verify they pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_name_refs.py -v -k "env_vars"
```

Expected: 7 PASS.

- [ ] **Step 1.5: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py
git commit -m "feat(SF-149): substitute_env_vars helper (DEMO-006)"
```

---

## Task 2: `substitute_response_vars(env=...)` — env-first fallback to entries

Make the existing helper consult `env` *before* the flat entries list. Backward-compatible: callers that don't pass `env` get the current behaviour.

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py`
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py`

- [ ] **Step 2.1: Write the failing tests**

Append to `test_name_refs.py`:

```python
# ---------------------------------------------------------------------------
# substitute_response_vars — env-first fallback to entries
# ---------------------------------------------------------------------------


def test_response_vars_env_hit_wins_over_entries() -> None:
    entries = [FanoutResponse(text="from-entry", name="x")]
    env = Env.root().child(x="from-env")
    # Env wins because it's checked first.
    assert substitute_response_vars("$x", entries, env=env) == "from-env"


def test_response_vars_entries_used_when_env_misses() -> None:
    entries = [FanoutResponse(text="from-entry", name="x")]
    env = Env.root().child(y="other")
    assert substitute_response_vars("$x", entries, env=env) == "from-entry"


def test_response_vars_all_miss_leaves_literal() -> None:
    entries = [FanoutResponse(text="t", name="other")]
    env = Env.root().child(y="other")
    assert substitute_response_vars("$x stays", entries, env=env) == "$x stays"


def test_response_vars_no_env_param_is_backward_compatible() -> None:
    """Existing callers that don't pass env get the original behavior."""
    entries = [FanoutResponse(text="hi", name="claude")]
    assert substitute_response_vars("$claude!", entries) == "hi!"


def test_response_vars_env_only_no_matching_entry() -> None:
    """An env binding is picked up even if no entry has that name."""
    env = Env.root().child(consensus="combined")
    assert (
        substitute_response_vars("reduce: $consensus", [], env=env) == "reduce: combined"
    )
```

- [ ] **Step 2.2: Run, verify they fail**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_name_refs.py -v -k "response_vars"
```

Expected: FAIL — current signature doesn't accept `env=`.

- [ ] **Step 2.3: Extend `substitute_response_vars`**

Edit `ensemble_helpers.py`. Replace the body of `substitute_response_vars`:

```python
def substitute_response_vars(
    instruction: str,
    entries: list[FanoutResponse],
    env: Env | None = None,
) -> str:
    """Replace ``$name`` tokens in ``instruction`` with bound values.

    SF-90 + DEMO-006 (SF-149): unified ``$<name>`` resolution.

    Lookup order per token:

    1. ``env.lookup(name)`` — DEMO-005 bindings (named scope frames)
    2. The matching ``FanoutResponse.name`` from ``entries`` — the
       legacy ensemble fan-out behaviour
    3. Leave the token literal — the LLM sees it as text

    Step 3 is intentional. Existing tests rely on missing references
    passing through unchanged; surprise-erroring would break them.

    Non-string env values are JSON-encoded (matches
    :func:`substitute_item`).
    """
    if not instruction:
        return instruction

    # Build a name → text map from entries so the regex pass can do an
    # O(1) lookup per token rather than scanning the list each time.
    entry_map: dict[str, str] = {
        e.name: e.text.strip() for e in entries if e.name is not None
    }

    def _repl(match: re.Match) -> str:
        name = match.group(1)
        if env is not None:
            try:
                value = env.lookup(name)
            except KeyError:
                pass
            else:
                return value if isinstance(value, str) else json.dumps(value)
        if name in entry_map:
            return entry_map[name]
        return match.group(0)

    return _NAME_REF_RE.sub(_repl, instruction)
```

This replaces the previous loop-based implementation with a single regex pass. Behaviour for env-less calls is identical: missing names stay literal, known names substitute. The previous implementation also `strip()`-ed each entry's text — preserved here.

- [ ] **Step 2.4: Run all response_vars tests, verify pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_name_refs.py -v -k "response_vars"
uv run pytest src/screamingface/plugins/url4_executor/tests/test_ensemble.py -v -k "substitute_response_vars or SubstituteResponseVars or substitute_response"
```

Expected: all new + legacy tests PASS.

- [ ] **Step 2.5: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py
git commit -m "feat(SF-149): substitute_response_vars consults env first (DEMO-006)"
```

---

## Task 3: Multi-segment `$item.foo.bar` dotted access

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py`
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py`

- [ ] **Step 3.1: Write the failing tests**

Append to `test_name_refs.py`:

```python
# ---------------------------------------------------------------------------
# substitute_item — multi-segment dotted
# ---------------------------------------------------------------------------


def test_item_three_segment_hit() -> None:
    result = substitute_item("$item.a.b.c", '{"a":{"b":{"c":"x"}}}')
    assert result == "x"


def test_item_two_segment_hit() -> None:
    result = substitute_item("$item.user.name", '{"user":{"name":"Alice"}}')
    assert result == "Alice"


def test_item_three_segment_graceful_miss_intermediate_not_dict() -> None:
    # `a` exists but is `1`, not a dict — leave the whole token literal.
    assert substitute_item("$item.a.b.c", '{"a":1}') == "$item.a.b.c"


def test_item_three_segment_graceful_miss_terminal_absent() -> None:
    assert (
        substitute_item("$item.a.b.c", '{"a":{"b":{"d":1}}}')
        == "$item.a.b.c"
    )


def test_item_multi_segment_non_string_value_json_encoded() -> None:
    result = substitute_item("$item.a.b", '{"a":{"b":[1,2,3]}}')
    assert result == "[1, 2, 3]"


def test_item_single_segment_still_works() -> None:
    # Regression: existing single-segment behaviour unchanged.
    assert substitute_item("$item.q", '{"q":"hi"}') == "hi"


def test_item_bare_item_still_works() -> None:
    # Regression: bare $item unchanged.
    assert substitute_item("$item", "raw") == "raw"


def test_item_field_inside_text_still_works() -> None:
    result = substitute_item("Q: $item.q.", '{"q":"hello"}')
    assert result == "Q: hello."
```

- [ ] **Step 3.2: Run, verify failures**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_name_refs.py -v -k "item_"
```

Expected: most multi-segment tests FAIL because the current regex only handles one segment.

- [ ] **Step 3.3: Extend `substitute_item`**

Replace the body of `substitute_item` in `ensemble_helpers.py`:

```python
def substitute_item(template: str, item_json: str) -> str:
    """Replace ``$item`` / ``$item.a.b.c`` in ``template`` with values from ``item_json``.

    - ``$item`` alone → the full ``item_json`` string.
    - ``$item.a.b.c`` (one or more segments) → walks the parsed JSON
      dict recursively. If any intermediate value isn't a dict, or any
      segment is absent, the whole ``$item.a.b.c`` token is left
      literal.
    - Terminal non-string values are JSON-encoded (matches the
      original single-level behaviour).
    """
    # One or more `.segment` parts. Each segment is a Python-identifier.
    field_pattern = re.compile(r"\$item((?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)")
    parsed_item: dict | None = None
    parse_attempted = False

    def _ensure_parsed() -> None:
        nonlocal parsed_item, parse_attempted
        if parse_attempted:
            return
        parse_attempted = True
        try:
            loaded = json.loads(item_json)
        except (json.JSONDecodeError, TypeError):
            parsed_item = None
            return
        parsed_item = loaded if isinstance(loaded, dict) else None

    def _field_replacer(match: re.Match) -> str:
        _ensure_parsed()
        if parsed_item is None:
            return match.group(0)
        # match.group(1) is e.g. ".a.b.c" — split on dots, skip the empty
        # leading slot.
        segments = match.group(1).split(".")[1:]
        cursor: object = parsed_item
        for seg in segments:
            if not isinstance(cursor, dict) or seg not in cursor:
                return match.group(0)
            cursor = cursor[seg]
        return cursor if isinstance(cursor, str) else json.dumps(cursor)

    result = field_pattern.sub(_field_replacer, template)

    # Bare ``$item`` (not followed by ``.<identifier>``) substitution.
    bare_pattern = re.compile(r"\$item(?!\.[a-zA-Z_])")
    return bare_pattern.sub(item_json, result)
```

- [ ] **Step 3.4: Run all item tests, verify pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_name_refs.py -v -k "item_"
uv run pytest src/screamingface/plugins/url4_executor/tests/test_ensemble.py -v -k "SubstituteItem or substitute_item"
```

Expected: all new + legacy tests PASS.

- [ ] **Step 3.5: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py
git commit -m "feat(SF-149): multi-segment \$item.a.b.c dotted access (DEMO-006)"
```

---

## Task 4: `Url4Text` resolution runs env-aware substitution

The spec says any `$<name>` in any text-position resolves through env. Today `resolve(Url4Text)` returns `node.value` verbatim — bind it through `substitute_env_vars`.

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py`

- [ ] **Step 4.1: Write the failing tests**

Append to `test_name_refs.py`:

```python
# ---------------------------------------------------------------------------
# Url4Text resolution — env-aware substitution
# ---------------------------------------------------------------------------

import asyncio

from screamingface.plugins.url4_executor.url4 import parse
from screamingface.plugins.url4_executor.url4_resolve import resolve


def test_url4_text_substitutes_env_name() -> None:
    env = Env.root().child(greeting="hello")
    result = asyncio.run(resolve(parse("$greeting world"), app=None, env=env))
    assert result == "hello world"


def test_url4_text_unknown_name_left_literal() -> None:
    env = Env.root()
    result = asyncio.run(resolve(parse("$unknown stays"), app=None, env=env))
    assert result == "$unknown stays"


def test_list_binding_visible_to_sibling_text() -> None:
    """The whole-pipeline test: bind in pass 1, sibling text reads in pass 2.

    `(x=hi, see $x)` — pass 1 binds x="hi", pass 2 resolves the text
    `see $x` under a child Env that knows x.
    """
    result = asyncio.run(resolve(parse("(x=hi, see $x)"), app=None, env=Env.root()))
    assert result == "hi\nsee hi"
```

- [ ] **Step 4.2: Run, verify failures**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_name_refs.py -v -k "url4_text or list_binding_visible"
```

Expected: FAIL — `Url4Text` returns the literal value, so `$greeting world` comes back unchanged.

- [ ] **Step 4.3: Update `resolve(Url4Text)` to call `substitute_env_vars`**

Edit `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`. Add the import:

```python
from screamingface.plugins.url4_executor.ensemble_helpers import substitute_env_vars
```

Change the `Url4Text` branch in `resolve`:

```python
    if isinstance(node, Url4Text):
        return substitute_env_vars(node.value, env)
```

`substitute_env_vars` is a no-op when `env is None` or the text has no `$name` tokens, so it costs nothing for the common case.

- [ ] **Step 4.4: Run tests, verify pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_name_refs.py -v
```

Expected: all PASS.

- [ ] **Step 4.5: Regression — full url4_executor suite**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -q
```

Expected: all green. Pay attention to tests that constructed plain text containing literal `$` characters that aren't followed by an identifier; the regex requires `\$([a-zA-Z_]...)` so a bare `$` or `$1` is unaffected.

- [ ] **Step 4.6: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_name_refs.py
git commit -m "feat(SF-149): Url4Text resolution runs env-aware substitution (DEMO-006)"
```

---

## Task 5: Ensemble interpreter passes env into `substitute_response_vars`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble.py:271`

- [ ] **Step 5.1: Update the call site**

Edit `apps/server/src/screamingface/plugins/url4_executor/ensemble.py`, replace:

```python
            reducer_instruction = substitute_response_vars(reducer_instruction, response_entries)
```

with:

```python
            reducer_instruction = substitute_response_vars(
                reducer_instruction, response_entries, env=env
            )
```

- [ ] **Step 5.2: Run the ensemble tests**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_ensemble.py -q
```

Expected: all green.

- [ ] **Step 5.3: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/ensemble.py
git commit -m "feat(SF-149): ensemble — thread env into substitute_response_vars (DEMO-006)"
```

---

## Task 6: E2E — sibling reducer reads a binding

**Files:**
- Modify: `apps/server/tests/e2e/data/other/named_bindings.yaml`

- [ ] **Step 6.1: Append the new fixture**

Append to `apps/server/tests/e2e/data/other/named_bindings.yaml`:

```yaml
- id: sibling_text_reads_eq_binding
  description: "(x=hi, see $x) — sibling text resolves $x via env from the bound sibling"
  ticket: SF-149
  backends: []
  expression: "(x=hi, see $x)"
  expect:
    status: 200
    # Output is the binding value, then the sibling with $x substituted.
    contains_all: ["hi", "see hi"]

- id: sibling_text_reads_colon_binding
  description: "(group:(a, b), reduce $group) — sibling reads the joined group via env"
  ticket: SF-149
  backends: []
  expression: "(group:(a, b), reduce $group)"
  expect:
    status: 200
    contains_all: ["a", "b", "reduce a"]
```

The second case asserts what the joined group looks like: `group` is bound to the list resolution `"a\nb"`, so the sibling `reduce $group` renders as `reduce a\nb`. The `contains_all` check is liberal (just substrings) so it doesn't pin the exact newline placement — but `reduce a` must appear as a substring after substitution.

- [ ] **Step 6.2: Run the new e2e cases**

```bash
cd apps/server
uv run pytest tests/e2e/test_url4_matrix.py -m "e2e and not live" -v -k "sibling_text"
```

Expected: both PASS.

- [ ] **Step 6.3: Commit**

```bash
git add apps/server/tests/e2e/data/other/named_bindings.yaml
git commit -m "test(SF-149): e2e — sibling reads sibling binding (DEMO-006)"
```

---

## Task 7: Final regression sweep, lint, push, PR

- [ ] **Step 7.1: Full url4_executor suite**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/ -v
```

Expected: all green.

- [ ] **Step 7.2: Full non-live e2e suite**

```bash
cd apps/server
uv run pytest tests/e2e/test_url4_matrix.py -m "e2e and not live" -q
```

Expected: all green.

- [ ] **Step 7.3: Pre-commit (ruff check + ruff format + pyright)**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
pre-commit run --from-ref origin/main --to-ref HEAD
```

Expected: PASS.

- [ ] **Step 7.4: Push and open PR (stop — do NOT merge)**

```bash
cd /Users/sergey/work/openmind/screamingface
git push -u origin SF-149-name-refs
gh pr create \
  --title "SF-149: \$<name> ref resolution + multi-segment \$item.a.b.c (DEMO-006)" \
  --body "$(cat <<'EOF'
## Summary
- New `substitute_env_vars(text, env)` helper — replaces every `$<name>` token in a text via `Env.lookup`, leaving unknown names literal.
- `substitute_response_vars` gains an optional `env=` param; lookup order per token is env → entries → literal. Backward compatible (no env = original behaviour).
- `substitute_item` extended from one-segment to multi-segment dotted: `$item.a.b.c` walks the parsed JSON dict recursively; any non-dict intermediate or missing terminal leaves the whole token literal.
- `Url4Text` resolution now runs `substitute_env_vars`, so text-position `$name` refs (not just reducer instructions) resolve through env.
- `_ensemble_evaluate` threads `env` into `substitute_response_vars`.
- 2 new e2e cases in `data/other/named_bindings.yaml` verify a sibling reads a binding declared earlier in the same list.

## Test plan
- [x] New unit tests in `tests/test_name_refs.py` — env vars, response vars with env, multi-segment item, Url4Text env-aware resolution
- [x] `uv run pytest src/screamingface/plugins/url4_executor/tests/` — green
- [x] `uv run pytest tests/e2e/test_url4_matrix.py -m "e2e and not live"` — green
- [x] `pre-commit run` — green

## References
- Spec: `/Users/sergey/.claude/plans/leaderboard-demo-tickets/DEMO-006-name-refs-and-dotted.md`
- Plan: `docs/superpowers/plans/2026-05-14-demo-006-name-refs-and-dotted.md`
- Builds on DEMO-005 (SF-152, PR #167)
EOF
)"
```

**Stop here** — user reviews and merges manually.

---

## Self-review notes

- **Spec coverage:**
  - `substitute_response_vars(env=...)` env-first → Task 2 ✓
  - `substitute_item` three-segment hit → Task 3 ✓
  - `substitute_item` graceful miss (intermediate not dict) → Task 3 ✓
  - `Url4Text` runs env-aware substitution → Task 4 ✓
  - Unit tests for env hit / env miss with entries fallback / all-miss literal / multi-level dotted hit / graceful miss → Tasks 1–3 ✓
  - All existing tests still green → Tasks 4.5, 7.1, 7.2 ✓
  - E2E case in `named_bindings.yaml` exercising sibling reading binding → Task 6 ✓
- **Order matters (spec §"Technical notes"):** `substitute_item` runs *before* generic `$name` because the call sites are different functions invoked in different places — `substitute_item` is called per collection-iteration body before `$name` substitution ever sees the result. Same ordering preserved.
- **Placeholders:** none.
- **Type/name consistency:** `substitute_env_vars(text, env)`, `substitute_response_vars(instruction, entries, env=None)`, `substitute_item(template, item_json)` — exact same names used across tasks, tests, call site, and YAML.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-14-demo-006-name-refs-and-dotted.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Fresh subagent per task, two-stage review between tasks.

**2. Inline Execution** — Execute tasks in this session via `superpowers:executing-plans`.

**Which approach?**
