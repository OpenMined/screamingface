# URL4 Reduced-Ensemble Binding (`name=(fanout)!reduce`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Allow a named binding's value to be a *reduced ensemble* — `name=(claude:0.40:/claude(q)!'…', codex:0.30:…, gemini:0.30:…)!'weighted reduce'` — so the URL4 scored query can bind a **3-way weighted consensus** to `$consensus` (today only a single-model consensus binds). This upgrades `ScoredLiveTruth` from v1-lite (single model) to the full weighted 3-way ensemble.

**Architecture:** The fan-out + weighted-reduce logic currently lives in `EnsembleInterpreter._ensemble_evaluate` (interpreter layer), but binding values are resolved by `resolve()` / `_resolve_list` (AST-walker layer, `url4_resolve.py`). A binding value that is a `(group)!reduce` therefore needs interpreter-level reduce from the walker layer — a layering seam. We resolve it by (1) **extracting** the fan-out+reduce core into a shared, dependency-neutral helper that both layers call, (2) adding a `Url4Reduce` AST node for `(group)!intent`, and (3) handling `Url4Reduce` in `resolve()`, threading the reducer-backend ("processor") through the `Env` so the walker can run a reduce without importing the interpreter (avoiding a circular dependency).

**Tech Stack:** Python 3.12/3.13, TatSu PEG grammar, the URL4 executor (`apps/server/src/screamingface/plugins/url4_executor/`), pytest (`@pytest.mark.asyncio`).

**Depends on:** PR #230 (SF-34 scored query engine) and PR #231 (`quoted` intent rule — the weighted-reduce prompt contains commas). This branch is stacked on both.

---

## Current state (verified against the code)

- `eq_value = group | atom_no_binding` (`url4_grammar.py:69-72`) — a binding value can be a group `(…)` **but not** a group with a trailing `!intent`. So `name=(fanout)!reduce` does not parse (the `!reduce` is left dangling).
- `EnsembleInterpreter._ensemble_evaluate(source_node, raw_intent, env)` (`ensemble.py:341-394`) is the weighted reduce: resolve the reducer instruction; `asyncio.gather(resolve(item) …)` over the backend calls; build `FanoutResponse` entries carrying `name`/`weight`; `substitute_response_vars` + `build_reducer_input` (emits `claude (weight=40): …`); dispatch `Url4BackendCall(path=self._processor, intent=reducer_input)` via `_dispatch_backend_call`.
- `_resolve_list` (`url4_resolve.py:62-105`) resolves binding values in pass 1 via `await resolve(item.value, app, current)`. `resolve()` has no case that performs a reduce. `_resolve_list` has no reference to the interpreter or its `_processor`.
- `Env` (`scope.py`) is a frozen dataclass `{bindings: dict, parent: Env|None}` with `lookup`/`child`/`root`. Already used to thread `__run_id__` (see `python_runner/plugin.py`), so threading `__processor__` follows an established pattern.
- `ensemble.py` imports from `url4_resolve.py` (`_dispatch_backend_call`). So `url4_resolve.py` **must not** import `ensemble.py` at module load — the shared reduce helper must live in a neutral module.

---

## Decision points (review before implementing)

- **D1 — Where the shared helper lives.** Put `resolve_ensemble(...)` in `ensemble_helpers.py` (already dependency-neutral: imports only `json`/`re`/`dataclass`; already home to `build_reducer_input`/`FanoutResponse`). It will need `resolve` + `_dispatch_backend_call` from `url4_resolve.py` — import those **inside** the function (local import) to avoid a load-time cycle, mirroring how `ensemble.py` already does local imports.
- **D2 — How the walker gets the reducer backend ("processor").** Thread it via `Env`: `EnsembleInterpreter.evaluate` seeds `__processor__` into the root env once (like `__run_id__`); `resolve()`'s `Url4Reduce` case reads `env.lookup("__processor__")`, falling back to a sensible default (`/claude`) if absent. *(Alternative: thread an `interpreter` reference — rejected: couples the walker to the interpreter class.)*
- **D3 — Broadcast (`!*`) on a binding value.** Out of scope for v1 of this feature (the 3-way query needs only `!reduce`). The grammar rule will capture a `broadcast` flag for forward-compat, but `resolve()` may raise a clear `NotImplementedError` for `name=(group)!*…` until needed.

---

## File Structure

**Modify:**
- `apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py` — add `resolve_ensemble(...)` (the extracted fan-out+reduce core).
- `apps/server/src/screamingface/plugins/url4_executor/ensemble.py` — `_ensemble_evaluate` delegates to `resolve_ensemble`; `evaluate` seeds `__processor__` into env.
- `apps/server/src/screamingface/plugins/url4_executor/url4_ast.py` — add `Url4Reduce`.
- `apps/server/src/screamingface/plugins/url4_executor/url4_grammar.py` — `eq_value` gains a group-with-intent form + semantics → `Url4Reduce`.
- `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py` — `resolve()` handles `Url4Reduce`.
- `apps/server/src/screamingface/plugins/url4_executor/scope.py` — (only if a typed accessor is wanted; otherwise `__processor__` rides in `bindings`).
- `apps/server/sf.json` — upgrade `ScoredLiveTruth` to the 3-way weighted form (M4).

**Create (tests):**
- `.../tests/test_reduced_ensemble_binding.py` (grammar + eval + integration)

---

## Milestone 1 — Extract the fan-out+reduce core (no behavior change)

**Why:** Make the weighted reduce callable from the walker layer without a circular import.

### Task 1.1: `resolve_ensemble` helper

**Files:** Modify `ensemble_helpers.py`; Test `tests/test_reduced_ensemble_binding.py` (create).

- [ ] **Step 1 — Failing test** (calls the helper directly with a fake app):

```python
import pytest
from screamingface.plugins.url4_executor.ensemble_helpers import resolve_ensemble
from screamingface.plugins.url4_executor.url4_grammar import parse
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.tests.test_ensemble import _FakeDispatchPlugin, _make_app


@pytest.mark.asyncio
async def test_resolve_ensemble_fans_out_and_reduces():
    # 3 sources answer; the processor (also fake) returns a reduced answer.
    claude = _FakeDispatchPlugin(name="claude", paths=["/claude"], responses=["A", "B", "C", "REDUCED"])
    app = _make_app(claude)
    group = parse("(claude:0.40:/claude(q)!'a', claude:0.30:/claude(q)!'b', claude:0.30:/claude(q)!'c')")
    out = await resolve_ensemble(group.items, "Combine these.", processor="/claude", app=app, env=Env.root())
    assert out == "REDUCED"            # the processor's reduce output
    assert len(claude.calls) == 4      # 3 fan-out + 1 reduce
```

- [ ] **Step 2 — Run, verify fail** (`ImportError`).

- [ ] **Step 3 — Implement** `resolve_ensemble` in `ensemble_helpers.py` by lifting the body of `_ensemble_evaluate` (`ensemble.py:364-394`), parameterising the processor. Use LOCAL imports for `resolve`/`_dispatch_backend_call`/`Url4Text` to avoid a load-time cycle:

```python
async def resolve_ensemble(items, reducer_instruction, *, processor, app, env=None):
    """Fan-out the backend-call ``items`` in parallel, then reduce via
    ``processor`` using weighted-label reducer input. Returns the reducer's
    text. Dependency-neutral: imports resolve/dispatch locally."""
    import asyncio
    from screamingface.plugins.url4_executor.url4 import Url4Text
    from screamingface.plugins.url4_executor.url4_ast import Url4BackendCall
    from screamingface.plugins.url4_executor.url4_resolve import _dispatch_backend_call, resolve

    responses = list(await asyncio.gather(*[resolve(it, app, env) for it in items]))
    entries = [
        FanoutResponse(
            text=resp,
            name=it.name if isinstance(it, Url4BackendCall) else None,
            weight=it.weight if isinstance(it, Url4BackendCall) else None,
        )
        for it, resp in zip(items, responses, strict=True)
    ]
    instruction = substitute_response_vars(reducer_instruction, entries)
    reducer_input = build_reducer_input(entries, instruction)
    reducer_node = Url4BackendCall(path=processor, intent=Url4Text(value=reducer_input))
    return await _dispatch_backend_call(reducer_node, app, env)
```

- [ ] **Step 4 — Run, verify pass.**

- [ ] **Step 5 — Refactor `_ensemble_evaluate` to delegate** (preserve its tracing + `resolve_intent` of the raw intent; only the fan-out+reduce body moves):

```python
reducer_instruction = await resolve_intent(raw_intent, self.app, env) if raw_intent else ""
return await resolve_ensemble(
    source_node.items, reducer_instruction, processor=self._processor, app=self.app, env=env
)
```

- [ ] **Step 6 — Regression** (`pytest src/screamingface/plugins/url4_executor/tests/ -q`): all existing ensemble/fan-out tests must stay green (the delegation must be byte-for-byte equivalent). Commit.

```bash
git commit -m "refactor(url4): extract resolve_ensemble core from _ensemble_evaluate"
```

---

## Milestone 2 — `Url4Reduce` AST + grammar `eq_value` form

### Task 2.1: AST node

**Files:** Modify `url4_ast.py`; Test in `tests/test_reduced_ensemble_binding.py`.

- [ ] **Step 1 — Failing test** (parse a binding whose value is `(group)!reduce`):

```python
from screamingface.plugins.url4_executor.url4_ast import Url4Binding, Url4Reduce, Url4BackendCall


def test_binding_value_group_with_intent_parses_to_reduce():
    node = parse("(consensus=(claude:0.40:/claude(q)!'a', codex:0.30:/codex(q)!'b')!'reduce, weighted')")
    binding = node.items[0]
    assert isinstance(binding, Url4Binding) and binding.name == "consensus"
    rv = binding.value
    assert isinstance(rv, Url4Reduce)
    assert len(rv.items) == 2 and all(isinstance(i, Url4BackendCall) for i in rv.items)
    assert rv.intent.value == "'reduce, weighted'"   # quoted rule (PR #231) keeps the comma
    assert rv.broadcast is False
```

- [ ] **Step 2 — Run, verify fail.**

- [ ] **Step 3 — Add `Url4Reduce`** to `url4_ast.py` (frozen dataclass, mirror the existing node style):

```python
@dataclass(frozen=True)
class Url4Reduce(Url4Node):
    """A group with a trailing reduce intent: ``(a, b, c)!intent``.
    Used as a binding value so a name can bind a reduced ensemble."""
    items: tuple[Url4Node, ...]
    intent: Url4Node | None
    broadcast: bool = False
```
Export it where the other nodes are exported.

- [ ] **Step 4 — Grammar.** In `url4_grammar.py`, extend `eq_value` (put the new form FIRST so it wins over bare `group`):

```
    eq_value
        = grouped_reduce
        | group
        | atom_no_binding
        ;

    grouped_reduce = grp:group '!' [ star:'*' ] intent:atom_no_bc ;
```
Add the semantics. `grp` is the already-built `Url4List` (from the `group` rule's semantic action), so reuse its `items`:

```python
    def grouped_reduce(self, ast):
        grp = ast.grp                      # Url4List
        items = grp.items if isinstance(grp, Url4List) else ()
        return Url4Reduce(items=items, intent=ast.intent, broadcast=bool(getattr(ast, "star", None)))
```
Import `Url4Reduce` in `url4_grammar.py`.

> Disambiguation note: `eq_value` is only reached after `name=` in a `binding`. The `grouped_reduce` form requires `(` next (a group), so it cannot collide with `atom_no_binding` (which never starts with `(` except via `group`). Putting `grouped_reduce` before `group` makes a group **with** a trailing `!` bind as a reduce, while a bare group still binds as a list.

- [ ] **Step 5 — Run, verify pass.** Regression (grammar change!): `pytest src/screamingface/plugins/url4_executor/tests/ -q` — must stay green. Commit.

```bash
git commit -m "feat(url4): Url4Reduce AST + eq_value group-with-intent form"
```

---

## Milestone 3 — Resolve `Url4Reduce` (thread the processor via Env)

### Task 3.1: `evaluate` seeds `__processor__`; `resolve()` handles `Url4Reduce`

**Files:** Modify `ensemble.py` (seed env), `url4_resolve.py` (resolve case); Test in `tests/test_reduced_ensemble_binding.py`.

- [ ] **Step 1 — Failing test** (a binding to a reduced ensemble resolves to the reduced value, available as `$name`):

```python
@pytest.mark.asyncio
async def test_binding_reduced_ensemble_resolves_to_consensus():
    claude = _FakeDispatchPlugin(name="claude", paths=["/claude"], responses=["Paris", "Parris", "REDUCED-Paris"])
    py = _FakeDispatchPlugin(name="python-runner", paths=["/python"], responses=["ok"])
    app = _make_app(claude, py)
    interp = EnsembleInterpreter(app=app)
    # bind consensus to a reduced 2-source ensemble, then pass $consensus to /python
    expr = ("(consensus=(claude:0.6:/claude(q)!'a', claude:0.4:/claude(q)!'b')!'combine weighted', "
            "/python(/data/code/x.py)!{\"c\":\"$consensus\"})")
    await interp.evaluate(expr)
    py_call = [c for c in py.calls if "/python" in c[1] or "x.py" in c[1]][0]
    assert py_call[0] == '{"c":"REDUCED-Paris"}'    # $consensus = the reducer output
    assert len(claude.calls) == 3                    # 2 fan-out + 1 reduce
```

- [ ] **Step 2 — Run, verify fail** (no `Url4Reduce` handling → `$consensus` unresolved or error).

- [ ] **Step 3 — Seed the processor.** In `EnsembleInterpreter.evaluate` (where `env` is defaulted to `Env.root()`), seed the processor once if absent:

```python
if env is None:
    env = Env.root()
try:
    env.lookup("__processor__")
except KeyError:
    env = env.child(__processor__=self._processor)
```

- [ ] **Step 4 — Handle `Url4Reduce` in `resolve()`** (`url4_resolve.py`). Add a case (local import of the helper to avoid a cycle):

```python
elif isinstance(node, Url4Reduce):
    if node.broadcast:
        raise NotImplementedError("name=(group)!*intent (broadcast binding) not supported yet")
    from screamingface.plugins.url4_executor.ensemble_helpers import resolve_ensemble
    from screamingface.plugins.url4_executor.interpreter import resolve_intent
    processor = "/claude"
    if env is not None:
        try:
            processor = env.lookup("__processor__")
        except KeyError:
            pass
    reducer_instruction = await resolve_intent(_node_to_intent_str(node.intent), app, env) if node.intent else ""
    return await resolve_ensemble(node.items, reducer_instruction, processor=processor, app=app, env=env)
```
`node.intent` is an AST node (`Url4Text` with the quoted reduce string); resolve it to the instruction text the same way intents are resolved elsewhere. If a tiny helper is needed to get the raw string from the `Url4Text`, use `node.intent.value` and strip quotes (reuse `resolve_intent`'s text path), matching how `_ensemble_evaluate` resolves `raw_intent`.

- [ ] **Step 5 — Run, verify pass.** Regression green. Commit.

```bash
git commit -m "feat(url4): resolve name=(fanout)!reduce binding to a reduced ensemble (SF-34)"
```

---

## Milestone 4 — Upgrade `ScoredLiveTruth` to the 3-way weighted ensemble

### Task 4.1: swap the spec + an integration test

**Files:** Modify `apps/server/sf.json`; Test in `tests/test_reduced_ensemble_binding.py` (or extend `tests/e2e/test_scored_query.py`).

- [ ] **Step 1 — Update the spec** deterministically (the comma in the reduce prompt now parses thanks to PR #231's quoted rule):

```python
# build script — replace ScoredLiveTruth.expression with the 3-way form:
PROMPT = "Answer this fill-in-the-blank question with the single most likely short answer. Return only the answer, no other text."
REDUCE = "Combine these candidate answers, weighting claude=0.40 codex=0.30 gemini=0.30, into the single best short answer. Return only the answer, no other text."
consensus = ("consensus=("
             f"claude:0.40:/claude($item.question)!'{PROMPT}', "
             f"codex:0.30:/codex($item.question)!'{PROMPT}', "
             f"gemini:0.30:/gemini($item.question)!'{PROMPT}')!'{REDUCE}'")
body = f"{consensus}, /python(/data/code/check_correct.py)!{{…same payload…}}"
expr = f"({DATASET}*({body}) ;foreach.concurrency=10;foreach.on_error=collect)!/python(/data/code/calculate_accuracy.py)"
```

- [ ] **Step 2 — Offline parse-check** the new spec like `M7.1` did (trace `split_intent` → `_strip_one_paren_layer` → `split_foreach_annotations` → `split_collection_iteration`, then `parse((row_body))` and assert the body is `[Url4Binding(consensus→Url4Reduce), Url4BackendCall(check)]`).

- [ ] **Step 3 — Extend the E2E test** (`tests/e2e/test_scored_query.py`): add fake `/codex` + `/gemini` plugins (and a reducer response), confirm the per-row consensus is the **reduced** value and accuracy is computed end-to-end. Keep the existing v1-lite test or replace it.

- [ ] **Step 4 — Regression + commit.**

```bash
git commit -m "feat(sf.json): ScoredLiveTruth uses 3-way weighted ensemble consensus"
```

---

## Self-Review checklist

- **Layering/cycle:** `ensemble_helpers.py` stays import-neutral at module load (local imports only). `url4_resolve.py` imports `resolve_ensemble` locally inside the `Url4Reduce` case. No new module-load cycle.
- **No behavior drift in M1:** `_ensemble_evaluate` delegates; all existing fan-out tests green.
- **Grammar additive:** `grouped_reduce` only matches a group followed by `!`; a bare group binding is unchanged. Full regression green after M2.
- **Processor default:** if `__processor__` isn't seeded (e.g. `resolve()` called outside the interpreter), the `/claude` fallback keeps reduce working; the interpreter path always seeds it.
- **Weights preserved:** `resolve_ensemble` builds `FanoutResponse` with `name`/`weight` → `build_reducer_input` emits the weighted labels, so the 3-way reduce is the proper weighted form (the whole point vs. the single-model v1-lite).

## Execution handoff

This is a focused 4-milestone feature. Recommended: **subagent-driven** (fresh subagent per task, spec + quality review between), stacked on PRs #230 + #231. After M4, open a third stacked PR. Live validation (real providers) still requires provider re-auth and is out of scope here.
