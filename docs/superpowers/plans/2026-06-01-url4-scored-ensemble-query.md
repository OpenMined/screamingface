# URL4 Scored-Ensemble Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the full scored-ensemble URL4 query run end-to-end over a dataset — per-row weighted ensemble → per-row correctness check → collection-level accuracy — and persist the result into Eval Studio, then store it as a named spec in `sf.json`.

**Architecture:** Extend the *existing* URL4 executor (decoder → dispatcher → `_collection_iterate` → backend dispatch) rather than rewriting the TatSu grammar. Five new/extended capabilities are added as independently-testable vertical slices: (1) generic `$name` substitution from the `Env` scope chain, (2) `;foreach.*` execution-annotation pre-parsing, (3) bounded concurrency + `on_error=collect` in collection iteration, (4) a new "collection-level reducer" evaluation shape that feeds the per-row result **array** to a final `/python` node, (5) a python-runner "call-`main()`" mode so the eval scripts run **unchanged** (imported as modules, `main()` invoked with introspected kwargs).

**Tech Stack:** Python 3.12/3.13, FastAPI, TatSu PEG (untouched here), `asyncio`, pytest (`@pytest.mark.asyncio`), the `screamingface` plugin framework, `python-runner` sandboxed subprocess executor.

---

> **Provenance & verification.** Grounded in the real code via a 5-agent research workflow, then adversarially verified by a 4-agent workflow (run `wf_ace0f409-fd7`). Architecture confirmed sound (~95% confidence): M3/M4 premises (per-row intent + abort-all gather; outer-paren wrapper hides `*(` so the new `_collection_reduce` branch is genuinely required), M1 premise (`$name` is fan-out-only today), and D2/D3 (script *fetch* vs `/python` *execute*; single stdin dict) all **confirmed against file:line**. Verification corrections already folded into this revision: exact `if name == "item"` check (no `startswith`); `@pytest.mark.asyncio` (project has `pytest-asyncio`, not `anyio`); `_FakeDispatchPlugin.calls` are `(intent, sources, app)` **tuples** (index `c[0]`/`c[1]`); shared `_fake_resolve_returning` helper defined; M4 `_maybe_json`/`_dispatch_backend_call_with_intent` + imports spelled out; robust `_repo_root()` instead of `parents[N]`; M5 `_resolve_list` binding-pollution fix made concrete. **Good news:** `__run_id__` is *already* threaded into the iteration env (`routes.py:105-106` → `ensemble.py:173`), so M7's eval-runs landing needs verification, not new wiring.

## ⚠️ Decision points (please review before implementation)

The query as written cannot run today for three *non-negotiable* reasons, plus two design choices I recommend. **These change the query text — please confirm.**

**D1 — Entry point: `/score` does not exist → use `/ensemble`.**
`grep` finds no `/score` route. The real URL4 entry point is `GET /ensemble?q=…` (`url4_executor/routes.py:85`). Port is `:8000` in dev, not `:8080`.

**D2 — `)!/data/check_correct.py` does not *execute* — it *fetches*.**
A bare `/data/...` intent parses as a relative-URL and is resolved by an HTTP GET (returns the script *source text*). To **run** a script it must be a `/python` backend call with the script URL as context and the JSON payload as intent:
`/python(/data/code/check_correct.py)!{…json…}`. Also the served path is `/data/code/<name>.py` (`python_runner/routes.py:34`), not `/data/<name>.py`.

**D3 — Two values into one python node: compose the payload; the runner calls `main()` with its declared params.**
`handle_backend_call` does `json.loads(intent)` → one dict; there is no auto-merge of separate `correct_answer=` / `consensus=` bindings. So the per-row call spells out the payload object, referencing the bound values:
`/python(/data/code/check_correct.py)!{"question":"$item.question","expected":"$item.expected_answer","correct_answer":"$item.expected_answer","consensus":"$consensus"}`.
Per your decision (M6, "Extend runner to call `main()`"), the runner imports the script and calls `main(**only-its-declared-params)`, so `check_correct.main(correct_answer, consensus)` gets exactly those two; the extra `question`/`expected` keys are ignored by `main()` and consumed by the eval-runs hook.

**D4 (RESOLVED — v1 drops the `normalized:`/validate layer).** With the livetruth free-text dataset there are no A/B/C/D probability distributions to validate or normalize, so the `normalized:(…)!*'Validate…'` + `$normalized` layer is **not applicable to v1**. v1 uses the proven MainOne-style weighted fan-out + reduce for `consensus`. (Revisit only if a multiple-choice dataset is introduced; `$name`-for-bindings still lands in M1 for `$consensus`.)

**D5 (recommended) — Implement `;foreach.*` by pre-parse extraction in the decoder, not a TatSu grammar production.**
Matches the codebase's existing "pre-parse before grammar" approach (`split_intent`, `split_collection_iteration` already work this way) and your "extend, don't invent" preference. The formal grammar production (SF-34 Phase 1.2) can follow later without reworking this.

### Canonical query this plan builds toward (v1, readable form)

```
( checks:https://screamingface.ai/livetruth-latest.eval.jsonl *(
    consensus=(
      claude:0.40:/claude($item.question)!'Answer this fill-in-the-blank question with the single most likely short answer. Return only the answer, no other text.',
      codex:0.30:/codex($item.question)!'Answer this fill-in-the-blank question with the single most likely short answer. Return only the answer, no other text.',
      gemini:0.30:/gemini($item.question)!'Answer this fill-in-the-blank question with the single most likely short answer. Return only the answer, no other text.'
    )!'These are candidate answers from sources weighted claude=0.40, codex=0.30, gemini=0.30. Return the single best short answer supported by the weighted majority. Return only the answer, no other text.',
    /python(/data/code/check_correct.py)!{"question":"$item.question","expected":"$item.expected_answer","correct_answer":"$item.expected_answer","consensus":"$consensus"}
  ) ;foreach.concurrency=10;foreach.on_error=collect
)!/python(/data/code/calculate_accuracy.py)
```

Per row the body is a 2-element list: bind `consensus` to the weighted ensemble result, then call `check_correct` with `$item.expected_answer` + `$consensus`. The collection then feeds all per-row verdicts as a JSON array to `calculate_accuracy`.

---

## Prerequisites (must be true before *testing* — not code tasks)

- [ ] **P1 — Provider re-auth.** After the last desktop restart the gateway lost its profiles (live probe: `claude` → "Gateway profile 'default' not found", `codex` → "rejected OAuth token", `gemini` → no response). Re-establish `claude`/`codex`/`gemini` auth profiles in the gateway (`POST /v1/auth/<provider>/profiles` / the desktop Providers panel) and confirm each returns HTTP 200 on a single `/ensemble?q=/<provider>(ok)` probe. *Without this, every row 502s regardless of code.*
- [x] **P2 — Dataset + field names (RESOLVED → livetruth).** `https://github.com/openmined/HLE.jsonl` returns **404** and no HLE dataset exists in the repo. **v1 targets `https://screamingface.ai/livetruth-latest.eval.jsonl`** (33 rows; fields `question` + `expected_answer`; free-text fill-in-the-blank, not A/B/C/D). Prompts return a **short answer** (not a letter); `check_correct`'s casefold string-equality scores free-text directly. `$item.expected_answer` → `$item.expected_answer` throughout.
- [ ] **P3 — Gemini model.** Already fixed: `aigw-gemini-backend.default_model = "gemini-cli/gemini-2.5-flash-lite"` in `sf.json` (larger Code Assist daily cap). Keep it; full fan-out over a dataset burns quota fast.

---

## Asana prerequisite mapping (SF-34 — all subtasks below are INCOMPLETE)

This query is a vertical slice of **SF-34 "URL4 spec v0.2 compliance: close 29 gaps in url4-executor"** (gid `1213822638119804`). The slice touches exactly these subtasks:

| Plan milestone | SF-34 subtask | gid |
|---|---|---|
| M1 generic `$name` substitution | Phase 1.4 — variable reference support (`$name`, `$N`) | `1213822906808012` |
| M2 `;foreach.*` annotations | Phase 1.2 — execution annotations (`;` separator) | `1213822913132370` |
| M3 concurrency + on_error | Phase 3.1 — `*` iteration operator + Phase 2.6 structured error codes | `1213822913199514`, `1213822907021603` |
| M4 collection-level reducer | Phase 3.1 + Phase 3.4 collection-level response envelope | `1213822913199514`, `1213822878733348` |
| M5 per-row payload (`name=` / `name:`) | Phase 1.1 attribution chain + Phase 1.5 `name=value` sugar | `1213822906890697`, `1213822913160822` |
| M-stretch `normalized:` validate layer | Phase 1.1 + Phase 1.4 (nested) | (as above) |

**Foundations already implemented in code** (even where the Asana task isn't tracked under that name): named bindings (`name=` / `name:` parse to `Url4Binding`), `$item` / `$item.field` substitution, `source*(body)` iteration, `!*` broadcast, weighted fan-out+reduce, `/python` + `/data/code/<name>.py` serving, the stdin/stdout runner contract, and the eval-runs `HOOK_QUESTION_CHECKED` pipeline. **SF-164** (end-to-end hookup, gid `1214568119302492`) is the integration milestone this plan effectively delivers.

> **Net:** finishing this plan completes the SF-34 subtasks listed above *for the constructs this query needs* (not the full 29-gap epic). Each milestone can land as its own PR and close/advance its subtask.

---

## File Structure

**Modify (executor core):**
- `apps/server/src/screamingface/plugins/url4_executor/decoder.py` — add `split_foreach_annotations()` (M2).
- `apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py` — add `substitute_env_vars()` (M1).
- `apps/server/src/screamingface/plugins/url4_executor/ensemble.py` — thread `Env` `$name` substitution (M1), concurrency/on_error in `_collection_iterate` (M3), new collection-reducer branch in `evaluate()` (M4).
- `apps/server/src/screamingface/plugins/url4_executor/interpreter.py` — `resolve_intent()` to consult `Env` for `$name` (M1).

**Scripts — used UNCHANGED (no edits):**
- `eval_scripts/check_correct.py`, `eval_scripts/calculate_accuracy.py` — installed verbatim under `python-runner.scripts`; the **runner** is extended to call their `main()` (M6).

**Modify (runner + config):**
- `apps/server/src/screamingface/plugins/python_runner/runner.py` — add `_script_defines_main` + `run_script_main` (call-main mode) (M6).
- `apps/server/src/screamingface/plugins/python_runner/sandbox/__init__.py` — `build_subprocess_argv` extra positional (M6).
- `apps/server/src/screamingface/plugins/python_runner/plugin.py` — dispatch to call-main when `main` is defined (M6).
- `apps/server/sf.json` — install the two scripts under `python-runner.scripts` (M6) and the named spec under `url4-specs.specs` (M7).

**Create (tests live beside the code under test):**
- `apps/server/src/screamingface/plugins/url4_executor/tests/test_env_vars.py` (M1)
- `.../tests/test_foreach_annotations.py` (M2)
- `.../tests/test_collection_concurrency.py` (M3)
- `.../tests/test_collection_reducer.py` (M4, M5)
- `apps/server/src/screamingface/plugins/python_runner/tests/test_call_main.py` (M6 — call-main mode)
- `apps/server/src/screamingface/plugins/python_runner/tests/test_eval_scripts.py` (M6 — real scripts via call-main)
- `apps/server/tests/e2e/test_scored_query.py` (M7)

**Test invocation conventions (observed in the repo):**
- Async tests use `@pytest.mark.asyncio`.
- Unit: call helpers directly, or `await EnsembleInterpreter(app=_make_app(plugin)).evaluate(expr)`.
- Backend mocking: `_FakeDispatchPlugin(name=…, paths=["/claude"], responses=[…])` (see `url4_executor/tests/test_ensemble.py`).
- E2E: FastAPI `TestClient.get("/ensemble", params={"q": expr})` with `create_app(config)`.
- Run a single file: `cd apps/server && PATH="$PWD/.venv/bin:$PATH" pytest src/screamingface/plugins/url4_executor/tests/test_env_vars.py -v`.
- Gates before every push (per project CI): `ruff check .` **and** `ruff format --check .` **and** `pyright` (whole package).

---

## Milestone 1 — Generic `$name` substitution from `Env`

**Why:** Today `$name` only resolves to *fan-out response names* via `substitute_response_vars` (`ensemble_helpers.py:89`). The query needs `$consensus` (a `name=` binding) and, in the stretch layer, `$normalized`. `Env.lookup` already exists (`scope.py:35`) but nothing substitutes `$name` text from it.

### Task 1.1: `substitute_env_vars()` helper

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py`
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_env_vars.py` (create)

- [ ] **Step 1 — Write the failing test**

```python
# apps/server/src/screamingface/plugins/url4_executor/tests/test_env_vars.py
from screamingface.plugins.url4_executor.ensemble_helpers import substitute_env_vars
from screamingface.plugins.url4_executor.scope import Env


def test_substitutes_named_binding_from_env():
    env = Env.root().child(consensus="B", normalized='{"A":0.1,"B":0.9}')
    out = substitute_env_vars('{"pick":"$consensus","dist":"$normalized"}', env)
    assert out == '{"pick":"B","dist":{"A":0.1,"B":0.9}}'.replace(
        '{"A":0.1,"B":0.9}', '{"A":0.1,"B":0.9}'
    )  # consensus replaced; normalized replaced verbatim


def test_unknown_name_left_as_is():
    env = Env.root().child(consensus="B")
    assert substitute_env_vars("$missing stays", env) == "$missing stays"


def test_item_is_reserved_but_item_id_resolves():
    env = Env.root().child(item_id="Y")  # no "item" key
    # $item_id resolves; bare $item is reserved (left untouched for substitute_item)
    assert substitute_env_vars("$item_id and $item", env) == "Y and $item"
```

- [ ] **Step 2 — Run it, verify it fails**

Run: `cd apps/server && PATH="$PWD/.venv/bin:$PATH" pytest src/screamingface/plugins/url4_executor/tests/test_env_vars.py -v`
Expected: FAIL — `ImportError: cannot import name 'substitute_env_vars'`.

- [ ] **Step 3 — Implement `substitute_env_vars`**

Add to `ensemble_helpers.py` (after `substitute_response_vars`). It must (a) skip `$item` / `$item.field` (those are handled by `substitute_item` during iteration), (b) match longest identifiers first, (c) leave unknown names untouched.

```python
def substitute_env_vars(text: str, env: "Env | None") -> str:
    """Replace ``$name`` tokens with values from the ``Env`` scope chain.

    Generalises SF-90's fan-out-only substitution to arbitrary named
    bindings (``name=`` / ``name:``) resolved via ``Env.lookup``.

    - ``$item`` / ``$item.<field>`` are NOT touched here (collection
      iteration owns those via ``substitute_item``).
    - Unknown names are left verbatim so they reach the model as text.
    - Non-string binding values are inserted via ``str(value)``.
    """
    if not text or env is None or "$" not in text:
        return text

    token = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")

    def _replace(m: "re.Match[str]") -> str:
        name = m.group(1)
        if name == "item":  # reserved: substitute_item owns $item / $item.field
            return m.group(0)
        try:
            value = env.lookup(name)
        except KeyError:
            return m.group(0)
        return value if isinstance(value, str) else str(value)

    return token.sub(_replace, text)
```

Add `"Env"` import guard at top (TYPE_CHECKING) and export `substitute_env_vars` in `__all__`.

> Why this is correct (verified against the codebase): the regex `\$([a-zA-Z_][a-zA-Z0-9_]*)` stops at the dot, so `$item.expected_answer` is captured as `item` → skipped (left for `substitute_item` during iteration), while `$item_id` and `$consensus` are captured whole and resolved from `Env`. Use exact `if name == "item":` — **not** `startswith("item")`, which would wrongly swallow `$item_id`.

- [ ] **Step 4 — Run tests, verify pass**

Run: `cd apps/server && PATH="$PWD/.venv/bin:$PATH" pytest src/screamingface/plugins/url4_executor/tests/test_env_vars.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5 — Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_env_vars.py
git commit -m "feat(url4): substitute \$name from Env scope chain (SF-34 Phase 1.4)"
```

### Task 1.2: Wire `$name` substitution into intent resolution

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/interpreter.py:21` (`resolve_intent`)
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py:121` (backend-call intent resolution)
- Test: append to `tests/test_env_vars.py`

- [ ] **Step 1 — Write the failing test** (an end-to-end-ish unit using a fake plugin)

```python
import pytest
from screamingface.plugins.url4_executor.ensemble import EnsembleInterpreter
from screamingface.plugins.url4_executor.tests.test_ensemble import _FakeDispatchPlugin, _make_app


@pytest.mark.asyncio
async def test_env_var_reaches_python_payload():
    # /python echoes its stdin payload back as text
    py = _FakeDispatchPlugin(name="python-runner", paths=["/python"], responses=["ECHO"])
    app = _make_app(py)
    interp = EnsembleInterpreter(app=app)
    # consensus bound to "B"; the python intent references $consensus
    expr = '(consensus=/claude(q)!ans, /python(/data/code/x.py)!{"c":"$consensus"})'
    await interp.evaluate(expr)
    # calls are (intent, sources, app) tuples; c[0] is the intent JSON
    assert any('"c":"' in c[0] and "$consensus" not in c[0] for c in py.calls)
```

*(`_FakeDispatchPlugin.calls` already records `(intent, sources, app)` tuples — no fixture change needed; index `c[0]`/`c[1]`.)*

- [ ] **Step 2 — Run, verify fail** (`$consensus` still present in captured intent).

- [ ] **Step 3 — Implement:** thread `env` into intent resolution and call `substitute_env_vars` after `$item` handling but before dispatch.

In `url4_resolve.py` where the backend-call intent is resolved (~line 121, `intent_text = await resolve(node.intent, app, env)`), add immediately after:

```python
from screamingface.plugins.url4_executor.ensemble_helpers import substitute_env_vars
intent_text = substitute_env_vars(intent_text, env)
```

In `interpreter.py:resolve_intent`, accept/propagate `env` (it already receives it per the trace) and apply `substitute_env_vars` to the resolved string before returning.

- [ ] **Step 4 — Run, verify pass.**

- [ ] **Step 5 — Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/interpreter.py \
        apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_env_vars.py
git commit -m "feat(url4): resolve \$name bindings in backend-call intents"
```

---

## Milestone 2 — `;foreach.*` execution-annotation pre-parsing

**Why:** `;foreach.concurrency=10;foreach.on_error=collect` currently parses as inert `Url4Text`. Extract it before grammar parsing (mirrors `split_intent`).

### Task 2.1: `split_foreach_annotations()`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/decoder.py`
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_foreach_annotations.py` (create)

- [ ] **Step 1 — Failing test**

```python
# tests/test_foreach_annotations.py
from screamingface.plugins.url4_executor.decoder import (
    ForeachDirectives,
    split_foreach_annotations,
)


def test_extracts_concurrency_and_on_error():
    clean, d = split_foreach_annotations("X;foreach.concurrency=10;foreach.on_error=collect")
    assert clean == "X"
    assert d == ForeachDirectives(concurrency=10, on_error="collect")


def test_absent_annotations_returns_defaults():
    clean, d = split_foreach_annotations("X")
    assert clean == "X"
    assert d == ForeachDirectives(concurrency=None, on_error="abort")


def test_semicolon_inside_parens_is_ignored():
    clean, d = split_foreach_annotations("(/claude(a;b)!x);foreach.concurrency=4")
    assert clean == "(/claude(a;b)!x)"
    assert d.concurrency == 4
```

- [ ] **Step 2 — Run, verify fail** (`ImportError`).

- [ ] **Step 3 — Implement** in `decoder.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ForeachDirectives:
    """Execution annotations for collection iteration (``;foreach.*``)."""
    concurrency: int | None = None
    on_error: str = "abort"  # "abort" (default) | "collect"


def split_foreach_annotations(expr: str) -> tuple[str, ForeachDirectives]:
    """Strip trailing ``;foreach.<key>=<value>`` directives (outside parens).

    Returns ``(clean_expr, ForeachDirectives)``. Unknown keys are ignored.
    Only ``;`` at paren-depth 0 are treated as directive separators.
    """
    depth = 0
    cut = len(expr)
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ";" and depth == 0:
            cut = i
            break
    if cut == len(expr):
        return expr, ForeachDirectives()

    clean = expr[:cut].strip()
    concurrency: int | None = None
    on_error = "abort"
    for part in expr[cut + 1 :].split(";"):
        part = part.strip()
        if part.startswith("foreach.concurrency="):
            try:
                concurrency = int(part.split("=", 1)[1])
            except ValueError:
                concurrency = None
        elif part.startswith("foreach.on_error="):
            on_error = part.split("=", 1)[1].strip()
    return clean, ForeachDirectives(concurrency=concurrency, on_error=on_error)
```

- [ ] **Step 4 — Run, verify pass** (3 tests).

- [ ] **Step 5 — Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/decoder.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_foreach_annotations.py
git commit -m "feat(url4): parse ;foreach.* execution annotations (SF-34 Phase 1.2)"
```

---

## Milestone 3 — Bounded concurrency + `on_error=collect` in iteration

**Why:** `_collection_iterate` uses `asyncio.gather(*…)` — unbounded and abort-on-first-error (`ensemble.py:175`). Apply the M2 directives.

### Task 3.1: thread directives + semaphore + error collection

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble.py` (`evaluate` dispatcher ~104-119, `_collection_iterate` 141-177)
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_collection_concurrency.py` (create)

- [ ] **Step 1 — Failing tests**

```python
# tests/test_collection_concurrency.py
import asyncio
import pytest
from screamingface.plugins.url4_executor.ensemble import EnsembleInterpreter
from screamingface.plugins.url4_executor.tests.test_ensemble import _FakeDispatchPlugin, _make_app


# Shared helper — reused verbatim by M3/M4/M5 (define here, import elsewhere).
# url4.resolve_str is `async def resolve_str(context, app, env=None)`; this stub
# returns a fixed collection body so parse_collection sees N rows.
def _fake_resolve_returning(content: str):
    async def _fake(context, app, env=None):
        return content
    return _fake


# NOTE on the test fixture: `_FakeDispatchPlugin.calls` records **tuples**
# `(intent, sources, app)` (see test_ensemble.py) — access by index: `c[0]`
# is the intent JSON string, `c[1]` is the sources URL. (Do NOT assume
# `.intent`/`.sources` attributes — that fixture uses plain tuples.)


@pytest.mark.asyncio
async def test_concurrency_cap_limits_in_flight(monkeypatch):
    # A 6-item collection with ;foreach.concurrency=2 must never exceed 2 in flight.
    inflight = {"now": 0, "max": 0}

    # patch the per-item evaluate to record concurrency
    ...

@pytest.mark.asyncio
async def test_on_error_collect_yields_error_element_not_abort():
    # One row raises; with on_error=collect the run completes and the
    # failing row appears as a structured {"error": ...} element.
    ...
```

*(Fill these with the repo's existing collection-iteration test fixtures from `test_ensemble.py`; the dataset is mocked via `monkeypatch` of `resolve_str` to return a small JSONL, exactly as existing iteration tests do.)*

- [ ] **Step 2 — Run, verify fail.**

- [ ] **Step 3 — Implement.** In `evaluate()`, extract directives before collection split:

```python
from screamingface.plugins.url4_executor.decoder import split_foreach_annotations, split_intent
...
source_expr, raw_intent, broadcast = split_intent(expr.strip())
source_expr, directives = split_foreach_annotations(source_expr)
```

Pass `directives` to `_collection_iterate(..., directives=directives)`. Replace the gather in `_collection_iterate`:

```python
sem = asyncio.Semaphore(directives.concurrency) if directives.concurrency else None

async def _guarded(item_json: str) -> str:
    if sem is None:
        return await _process_one(item_json)
    async with sem:
        return await _process_one(item_json)

if directives.on_error == "collect":
    raw = await asyncio.gather(*[_guarded(i) for i in items], return_exceptions=True)
    results = [
        r if not isinstance(r, BaseException)
        else json.dumps({"error": {"kind": type(r).__name__, "message": str(r)}})
        for r in raw
    ]
else:
    results = list(await asyncio.gather(*[_guarded(i) for i in items]))
```

(Add `import json` if not present.) Keep `"\n".join(results)` for the plain per-row case — M4 changes how results are surfaced when a collection-level reducer is present.

- [ ] **Step 4 — Run, verify pass.**

- [ ] **Step 5 — Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/ensemble.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_collection_concurrency.py
git commit -m "feat(url4): bounded concurrency + on_error=collect for iteration (SF-34 Phase 3.1/2.6)"
```

---

## Milestone 4 — Collection-level reducer over the per-row array

**Why:** The query is `( COLLECTION*(BODY)!perRow ;ann )!collectionReducer`. The outer `(...)` hides the `*(` from `split_collection_iteration` (it only matches depth 0), and even unwrapped, a trailing intent is applied *per row*, never to the **array** of rows. This is the genuinely new shape.

### Task 4.1: detect wrapped collection iteration + structured array passing

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble.py` (`evaluate` dispatcher; `_collection_iterate` to optionally return a JSON array; new `_collection_reduce` helper)
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_collection_reducer.py` (create)

- [ ] **Step 1 — Failing test**

```python
# tests/test_collection_reducer.py
import json
import pytest
from screamingface.plugins.url4_executor.ensemble import EnsembleInterpreter
from screamingface.plugins.url4_executor.tests.test_ensemble import _FakeDispatchPlugin, _make_app
from screamingface.plugins.url4_executor.tests.test_collection_concurrency import (
    _fake_resolve_returning,  # shared stub from M3
)


@pytest.mark.asyncio
async def test_collection_reducer_receives_json_array(monkeypatch):
    # 3-item dataset; per-row body returns a verdict dict; the outer
    # /python(calculate_accuracy) must receive a JSON ARRAY of 3 verdicts.
    py = _FakeDispatchPlugin(name="python-runner", paths=["/python"], responses=["AGG"])
    app = _make_app(py)
    # mock dataset fetch -> 3 JSONL rows
    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning('{"q":"1"}\n{"q":"2"}\n{"q":"3"}'),
    )
    interp = EnsembleInterpreter(app=app)
    expr = '(D*(/python(/data/code/c.py)!{"row":"$item.q"}))!/python(/data/code/agg.py)'
    await interp.evaluate(expr)
    agg_call = py.calls[-1]  # the reducer call
    payload = json.loads(agg_call.intent)
    assert isinstance(payload, list) and len(payload) == 3
```

- [ ] **Step 2 — Run, verify fail.**

- [ ] **Step 3 — Implement.** In `evaluate()`, after `split_foreach_annotations`, detect the wrapped-iteration-with-reducer shape:

```python
# 1b. Collection-level reducer: "(COLLECTION*(BODY)!perRow)!reducer"
inner = _strip_one_paren_layer(source_expr)  # returns inner or None
if inner is not None and raw_intent is not None:
    inner_src, inner_intent, _ = split_intent(inner)
    coll_src, coll_body = split_collection_iteration(inner_src)
    if coll_src is not None and coll_body is not None:
        rows = await self._collection_iterate(
            coll_src, coll_body, inner_intent or "", env,
            directives=directives, as_array=True,
        )  # returns list[str]
        return await self._collection_reduce(rows, raw_intent, env)
```

Add `as_array: bool = False` to `_collection_iterate`; when true, return the `results` list instead of `"\n".join`. Add helpers:

```python
def _strip_one_paren_layer(expr: str) -> str | None:
    """If ``expr`` is exactly one balanced ``(...)`` group, return its
    interior; else ``None``. Used to peek past the outer wrapper."""
    e = expr.strip()
    if not (e.startswith("(") and e.endswith(")")):
        return None
    depth = 0
    for i, ch in enumerate(e):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and i != len(e) - 1:
                return None  # closes early -> not a single wrapping group
    return e[1:-1]


async def _collection_reduce(self, rows: list[str], reducer_intent: str, env) -> str:
    """Feed the per-row result array to a collection-level reducer node.

    Each row string is parsed to JSON when possible so the reducer
    receives a real array of objects; otherwise the raw string is kept.
    """
    payload = [self._maybe_json(r) for r in rows]
    array_json = json.dumps(payload)
    reducer_src, reducer_payload, _ = split_intent(reducer_intent)
    # reducer is a /python(...) node: dispatch with the array as its intent
    node = parse(reducer_src)
    if isinstance(node, Url4BackendCall):
        return await _dispatch_backend_call_with_intent(node, array_json, self.app, env)
    # text reducer fallback: hand the array to the default reducer model
    return await self.process(array_json, reducer_intent, env)
```

Add these helpers (complete, no placeholders). In `ensemble.py` add imports at module top if absent:

```python
from screamingface.plugins.url4_executor.decoder import split_intent
from screamingface.plugins.url4_executor.url4 import parse
from screamingface.plugins.url4_executor.url4_ast import Url4BackendCall, Url4Text
from screamingface.plugins.url4_executor.url4_resolve import _dispatch_backend_call_with_intent
```

`_maybe_json` (static method on `EnsembleInterpreter`):

```python
@staticmethod
def _maybe_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
```

`_dispatch_backend_call_with_intent` in `url4_resolve.py`, next to `_dispatch_backend_call` (reuses its plugin lookup by overriding the node's intent with the array payload):

```python
async def _dispatch_backend_call_with_intent(node, intent_json: str, app, env=None) -> str:
    """Dispatch a backend_call but with its intent replaced by ``intent_json``.

    Used by the collection-level reducer: the per-row result array is
    handed to the reducer node (e.g. /python(calculate_accuracy.py)) as
    its stdin payload.
    """
    from screamingface.plugins.url4_executor.url4_ast import Url4BackendCall, Url4Text
    replaced = Url4BackendCall(
        path=node.path,
        packed_context=node.packed_context,
        intent=Url4Text(value=intent_json),
        name=node.name,
        weight=node.weight,
    )
    return await _dispatch_backend_call(replaced, app, env)
```

> Verify `Url4BackendCall`'s field names against `url4_ast.py:37-58` (`path`, `packed_context`, `intent`, `name`, `weight`) — pass exactly those; frozen dataclass.

- [ ] **Step 4 — Run, verify pass.**

- [ ] **Step 5 — Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/ensemble.py \
        apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_collection_reducer.py
git commit -m "feat(url4): collection-level reducer over per-row array (SF-34 Phase 3.1/3.4)"
```

---

## Milestone 5 — Per-row two-binding payload (end-to-end body)

**Why:** Verify the per-row body `(consensus=(ENSEMBLE), /python(check_correct)!{…$consensus…})` resolves: binding first (two-pass list resolution), then the python call with `$item.expected_answer` + `$consensus` substituted (M1). Mostly integration of M1+existing list resolution; this milestone is the test that locks it in and fixes any gaps found.

### Task 5.1: per-row binding → python payload integration test

**Files:**
- Test: append to `tests/test_collection_reducer.py`
- Modify (only if the test exposes a gap): `ensemble.py` list-result selection so a `(binding, call)` list returns the call's result.

- [ ] **Step 1 — Failing test**

```python
@pytest.mark.asyncio
async def test_per_row_consensus_and_check(monkeypatch):
    claude = _FakeDispatchPlugin(name="claude", paths=["/claude"], responses=["B", "B"])
    py = _FakeDispatchPlugin(name="python-runner", paths=["/python"], responses=['{"correct":true,"predicted":"B"}'] * 2)
    app = _make_app(claude, py)
    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning('{"question":"q1","answer":"B"}\n{"question":"q2","answer":"A"}'),
    )
    interp = EnsembleInterpreter(app=app)
    body = '(consensus=/claude($item.question)!pick, /python(/data/code/check_correct.py)!{"expected":"$item.expected_answer","consensus":"$consensus"})'
    await interp.evaluate(f"(D*{body})!/python(/data/code/calculate_accuracy.py)")
    # calls are (intent, sources, app) tuples; c[0]=intent JSON, c[1]=sources URL
    check_calls = [c for c in py.calls if "check_correct" in c[1]]
    assert all('"$consensus"' not in c[0] and "$item" not in c[0] for c in check_calls)
    assert any('"expected":"B"' in c[0] for c in check_calls)
```

- [ ] **Step 2 — Run, verify fail.** Expected failure (verified against code): `_resolve_list` (`url4_resolve.py:62-98`) ends with `return "\n".join(r for r in results if r is not None)` — it joins **both** binding values **and** non-binding results. So `(consensus=ENSEMBLE, /python(check))` returns *two* lines (the consensus text **and** the verdict), and the collection reducer then receives polluted rows.
- [ ] **Step 3 — Fix `_resolve_list` to return only non-binding results.** Track which result slots correspond to `Url4Binding` items and exclude them from the final join, so a `(binding, …, call)` list yields only the non-binding output(s):

```python
# url4_resolve.py _resolve_list (~line 62-98): when building `results`,
# record binding slots; exclude them from the returned join.
binding_slots = {i for i, item in enumerate(node.items) if isinstance(item, Url4Binding)}
return "\n".join(
    r for i, r in enumerate(results) if r is not None and i not in binding_slots
)
```

(`$item.expected_answer` is already substituted pre-parse by `substitute_item`; `$consensus` is substituted at dispatch by M1 — this step only removes the binding-value pollution.) Add `from screamingface.plugins.url4_executor.url4_ast import Url4Binding` if not already imported.
- [ ] **Step 4 — Run, verify pass.**
- [ ] **Step 5 — Commit**

```bash
git commit -am "test(url4): lock per-row two-binding python payload"
```

---

## Milestone 6 — Extend python-runner to call `main()` with named bindings (scripts UNCHANGED)

**Why:** `eval_scripts/check_correct.py` and `calculate_accuracy.py` are the **canonical** scoring logic and must be used **byte-for-byte as written**, keeping their `main(correct_answer, consensus)` / `main(checks)` signatures. Their docstrings define the contract: *"the node defines it in a sandbox and calls `main()` with the bound values as arguments — not via argv or stdin."* The current runner only does subprocess stdin/stdout, and would execute the scripts' `__main__` self-test → `invalid_output`. **Decision (chosen by the user): extend the runner, not the scripts.** The runner imports the script as a module (so its `__main__` block is skipped — zero edits), introspects `main()`'s signature, and calls `main(**only-its-declared-params)`. Extra payload keys (`question`/`expected`, needed by the eval-runs hook) are ignored by `main()` but remain available to the hook. Sandboxing is preserved.

### Task 6.1: add a "call `main()`" execution mode to the runner

**Files:**
- Modify: `apps/server/src/screamingface/plugins/python_runner/runner.py`
- Modify: `apps/server/src/screamingface/plugins/python_runner/sandbox/__init__.py` (`build_subprocess_argv` takes an extra positional)
- Test: `apps/server/src/screamingface/plugins/python_runner/tests/test_call_main.py` (create)

- [ ] **Step 1 — Failing test** (a script with a `main()` signature AND a `__main__` self-test, like the real eval scripts)

```python
# python_runner/tests/test_call_main.py
import pytest
from screamingface.plugins.python_runner.runner import run_script_main

TWO_ARG = '''
def main(correct_answer, consensus):
    return {"correct": correct_answer.strip().casefold() == consensus.strip().casefold(),
            "predicted": consensus.strip()}

if __name__ == "__main__":
    raise SystemExit("self-test must NOT run under call-main")
'''

ONE_ARG = '''
def main(checks):
    rows = checks if isinstance(checks, list) else []
    return {"n": sum(1 for r in rows if isinstance(r.get("correct"), bool))}
'''


@pytest.mark.asyncio
async def test_call_main_filters_to_declared_params():
    # extra keys (question/expected) ignored; main gets only its params, and
    # the __main__ self-test does NOT run (script is imported as a module)
    out = await run_script_main(TWO_ARG, {"correct_answer": "B", "consensus": " b ",
                                          "question": "q", "expected": "B"})
    assert out == {"correct": True, "predicted": "b"}


@pytest.mark.asyncio
async def test_call_main_single_param_takes_bare_list():
    out = await run_script_main(ONE_ARG, [{"correct": True}, {"correct": False}, {"x": 1}])
    assert out == {"n": 2}
```

- [ ] **Step 2 — Run, verify fail** (`ImportError: cannot import name 'run_script_main'`).

- [ ] **Step 3 — Implement in `runner.py`** — an AST check + a static harness that imports the user script as a module (skipping its `__main__`) and invokes `main()` with introspected kwargs:

```python
import ast


def _script_defines_main(source: str) -> bool:
    """True if the source defines a top-level ``def main`` (call-main mode)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "main"
        for n in tree.body
    )


# Static harness. Imports the user script AS A MODULE via importlib (so its
# ``if __name__ == "__main__"`` self-test is skipped — zero script edits),
# then invokes main() with only its declared parameters.
_MAIN_HARNESS = (
    "import json, sys, inspect, importlib.util\n"
    "_spec = importlib.util.spec_from_file_location('_url4_user', sys.argv[1])\n"
    "_mod = importlib.util.module_from_spec(_spec)\n"
    "_spec.loader.exec_module(_mod)  # module import -> __main__ self-test skipped\n"
    "_payload = json.loads(sys.stdin.read() or 'null')\n"
    "_params = list(inspect.signature(_mod.main).parameters)\n"
    "if isinstance(_payload, dict):\n"
    "    _result = _mod.main(**{k: v for k, v in _payload.items() if k in _params})\n"
    "elif isinstance(_payload, list) and len(_params) == 1:\n"
    "    _result = _mod.main(_payload)\n"
    "else:\n"
    "    _result = _mod.main(_payload)\n"
    "sys.stdout.write(json.dumps(_result))\n"
)


async def run_script_main(source: str, payload, timeout: float = 30.0) -> dict:
    """Run ``source``'s ``main()`` with kwargs from ``payload`` (sandboxed).

    A single-parameter ``main`` receives a bare-list payload directly.
    """
    user_path = _cache_script(source)
    harness_path = _cache_script(_MAIN_HARNESS)
    argv = build_subprocess_argv(harness_path, extra_args=[str(user_path)])
    payload_bytes = json.dumps(payload).encode()
    # Spawn EXACTLY like run_script_source (runner.py:77-91): same asyncio
    # subprocess spawn over `argv`, feed `payload_bytes` to stdin, then the
    # same timeout / nonzero-exit / json.loads(stdout) handling
    # (runner.py:92-125), raising PythonRunnerError on failure. Return the dict.
```

Widen the sandbox argv builder in `sandbox/__init__.py` to accept extra positionals (append `*extra` after the script path in BOTH the sandboxed and plain branches):

```python
def build_subprocess_argv(script_path, extra_args=None):
    extra = [str(a) for a in (extra_args or [])]
    # sandboxed branch: ...existing sandbox wrapper..., str(script_path), *extra
    # plain branch:      [sys.executable, str(script_path), *extra]
```

Both `harness_path` and `user_path` live under the cache dir (`SPEC_ROOT`), which `macos.sb` already grants `file-read*` — **no sandbox-profile change needed**.

- [ ] **Step 4 — Run, verify pass.**
- [ ] **Step 5 — Commit** `git commit -am "feat(python-runner): call main() with introspected kwargs (scripts unchanged)"`

### Task 6.2: dispatch the REAL eval scripts through call-main mode (scripts unchanged)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/python_runner/plugin.py` (~line 150 — choose mode)
- Test: `apps/server/src/screamingface/plugins/python_runner/tests/test_eval_scripts.py` (create)

- [ ] **Step 1 — Failing test** (runs the ACTUAL eval scripts, byte-for-byte, via the new runner path)

```python
# python_runner/tests/test_eval_scripts.py
from pathlib import Path
import pytest
from screamingface.plugins.python_runner.runner import run_script_main


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "eval_scripts").is_dir():
            return parent
    raise RuntimeError("eval_scripts/ not found above test file")


CHECK = (_repo_root() / "eval_scripts" / "check_correct.py").read_text()
ACC = (_repo_root() / "eval_scripts" / "calculate_accuracy.py").read_text()


@pytest.mark.asyncio
async def test_real_check_correct_via_call_main():
    # canonical per-row payload: main() consumes correct_answer+consensus and
    # ignores question/expected (those exist only for the eval-runs hook)
    out = await run_script_main(CHECK, {"question": "q", "expected": "B",
                                        "correct_answer": "B", "consensus": " b "})
    assert out["correct"] is True
    assert out["predicted"] == "b"          # consensus, stripped
    assert out["ground_truth"] == "B"       # check_correct's own return key


@pytest.mark.asyncio
async def test_real_check_correct_mismatch():
    out = await run_script_main(CHECK, {"correct_answer": "A", "consensus": "B"})
    assert out["correct"] is False


@pytest.mark.asyncio
async def test_real_calculate_accuracy_bare_array():
    rows = [{"correct": True, "predicted": "A"},
            {"correct": False, "predicted": "B"},
            {"correct": True, "predicted": "C"},
            {"error": {"kind": "Timeout"}}]   # on_error=collect element
    out = await run_script_main(ACC, rows)     # bare array -> single-arg main(checks)
    assert out["n"] == 3 and out["n_correct"] == 2
    assert out["n_errors"] == 1
    assert abs(out["accuracy_pct"] - 66.67) < 0.01
```

*(`_repo_root()` walk avoids brittle `parents[N]` counting. These tests use the eval scripts **as-is** — no script edits.)*

- [ ] **Step 2 — Run, verify fail** (`run_script_main` not yet wired into dispatch; the plugin still uses stdin mode, so the scripts' `__main__` self-test prints `PASS/FAIL` → `invalid_output`).

- [ ] **Step 3 — Wire dispatch in `plugin.py`** (~line 150): choose call-main when the script defines `main`:

```python
from screamingface.plugins.python_runner.runner import run_script_main, _script_defines_main
...
if _script_defines_main(source):
    result = await run_script_main(source, payload)
else:
    result = await run_script_source(source, payload)
```

The eval-runs `HOOK_QUESTION_CHECKED` block (`plugin.py:185-210`) stays **unchanged** — it reads `question`/`expected` from the raw `intent` payload and `predicted`/`correct` from `result`; `check_correct.main` returns `predicted`+`correct`, so the hook still fires correctly.

- [ ] **Step 4 — Run, verify pass.**
- [ ] **Step 5 — Commit** `git commit -am "feat(python-runner): dispatch main()-style scripts via call-main mode"`

### Task 6.3: install both scripts in `sf.json`

**Files:** Modify `apps/server/sf.json`.

- [ ] **Step 1 — Add to `plugin_config["python-runner"]["scripts"]`** (create the block if absent; keys must match `^[a-zA-Z_][a-zA-Z0-9_]*$`). Values are the full script source as a single JSON string (newlines escaped). Generate them deterministically:

```bash
cd /Users/sergey/work/openmind/screamingface
python3 - <<'PY'
import json, pathlib
sf = pathlib.Path("apps/server/sf.json"); cfg = json.loads(sf.read_text())
pr = cfg["plugin_config"].setdefault("python-runner", {})
scripts = pr.setdefault("scripts", {})
scripts["check_correct"] = pathlib.Path("eval_scripts/check_correct.py").read_text()
scripts["calculate_accuracy"] = pathlib.Path("eval_scripts/calculate_accuracy.py").read_text()
sf.write_text(json.dumps(cfg, indent=2) + "\n")
print("installed:", list(scripts))
PY
```

- [ ] **Step 2 — Verify served** (after desktop restart): `curl -s 'http://127.0.0.1:8000/data/code/check_correct.py' | head -3` shows the new source.
- [ ] **Step 3 — Commit** `git commit -am "chore(sf.json): install check_correct + calculate_accuracy scripts"`

---

## Milestone 7 — Add the spec + Eval Studio landing (E2E)

**Why:** Store the canonical query as a named spec and confirm a real run persists per-row `correct`/`predicted` into `eval_runs` and surfaces in Eval Studio.

### Task 7.1: add the named spec to `sf.json`

**Files:** Modify `apps/server/sf.json` → `plugin_config["url4-specs"]["specs"]["ScoredLiveTruth"]`.

- [ ] **Step 1 — Add the spec** (single-line `expression`; commas inside quoted intents are fine). Use the canonical v1 query (Decision section), with `DATASET_URL` from P2. Build it deterministically to avoid escaping mistakes:

```bash
python3 - <<'PY'
import json, pathlib
sf = pathlib.Path("apps/server/sf.json"); cfg = json.loads(sf.read_text())
DATASET = "https://screamingface.ai/livetruth-latest.eval.jsonl"  # v1 (P2 resolved)
PROMPT = ("Answer this fill-in-the-blank question with the single most likely "
          "short answer. Return only the answer, no other text.")
REDUCE = ("These are candidate answers from sources weighted claude=0.40, "
          "codex=0.30, gemini=0.30. Return the single best short answer "
          "supported by the weighted majority. Return only the answer.")
body = (
    f"consensus=(claude:0.40:/claude($item.question)!'{PROMPT}',"
    f"codex:0.30:/codex($item.question)!'{PROMPT}',"
    f"gemini:0.30:/gemini($item.question)!'{PROMPT}')!'{REDUCE}',"
    "/python(/data/code/check_correct.py)!{\"question\":\"$item.question\","
    "\"expected\":\"$item.expected_answer\",\"correct_answer\":\"$item.expected_answer\",\"consensus\":\"$consensus\"}"
)
expr = (f"({DATASET}*({body}) ;foreach.concurrency=10;foreach.on_error=collect)"
        "!/python(/data/code/calculate_accuracy.py)")
cfg["plugin_config"]["url4-specs"]["specs"]["ScoredLiveTruth"] = {"expression": expr}
sf.write_text(json.dumps(cfg, indent=2) + "\n")
print("spec bytes:", len(expr))
PY
```

- [ ] **Step 2 — Restart desktop** (dev reads `apps/server/sf.json` at launch) and **parse-check**:
`curl -s 'http://127.0.0.1:8000/ensemble/highlight' --data-urlencode q@<(...)` returns tokens with no error. *(Use `?ast=true` on `/ensemble` to confirm structure without spending tokens.)*

### Task 7.2: E2E scored run with eval-runs

**Files:** `apps/server/tests/e2e/test_scored_query.py` (create).

- [ ] **Step 1 — Failing E2E test** using `create_app(config)` + `TestClient`, mocked backends, a 3-row dataset, asserting: (a) the response is the accuracy JSON from `calculate_accuracy`, (b) `EvalRun` row created (via `X-SF-Run-Id`/`X-SF-Run-Spec` headers), (c) 3 `EvalQuestion` rows with `correct`/`predicted` set (via `HOOK_QUESTION_CHECKED` fired by `check_correct.py` — note the hook only fires when `sources.endswith("/check_correct.py")` and `__run_id__` is in env: `python_runner/plugin.py:185`).
- [ ] **Step 2 — Run, verify fail.**
- [ ] **Step 3 — Integration (mostly already wired — verify, don't rebuild).** Verification finding: `__run_id__` is **already** seeded into the env at `url4_executor/routes.py:105-106` (`env = env.child(__run_id__=run_id, …)` when `X-SF-Run-Id` is present) and is propagated unchanged through `_collection_iterate` → per-row `evaluate(full_expr, env)` (`ensemble.py:173`) → `handle_backend_call`'s `env.lookup("__run_id__")`. So the hook fires **provided** the per-row call is a real `/python(/data/code/check_correct.py)` dispatch (M5) and the script is installed (M6.3). Fix only residual gaps the E2E surfaces (e.g. the `check_correct` payload must carry `question`/`expected` keys for the hook payload — already in the canonical query).
- [ ] **Step 4 — Run, verify pass.**
- [ ] **Step 5 — Commit** `git commit -am "test(e2e): scored ensemble query persists to eval_runs"`

### Task 7.3: live smoke (manual, needs P1 re-auth)

- [ ] After P1, run a **bounded** live check (3–5 rows) by pointing the spec at a tiny dataset, via:
`curl -sG 'http://127.0.0.1:8000/ensemble' -H 'X-SF-Run-Spec: ScoredLiveTruth' --data-urlencode q@<spec-expr>` and confirm: HTTP 200, an accuracy summary, no 429, and a run visible in Eval Studio. Keep row count small (gemini daily cap).

---

## Self-Review

**Spec coverage:** every construct in the target query maps to a milestone — `;foreach.*` → M2/M3; `$name` (`$consensus`/`$normalized`) → M1; `name=`/`name:` bindings → M5 (parse already supported); `*` iteration → existing + M3/M4; per-row python with two values → M5 (payload composed via D3); collection reducer → M4; scripts run **unchanged** via the runner's call-`main()` mode → M6; entry point + sf.json + Eval Studio → M7. The `normalized:`/`!*'Validate…'` layer is explicitly deferred to **M-stretch** (D4) — flagged, not silently dropped.

**Placeholder scan:** test bodies in M3/M4/M5 use `...` where they must be filled from the repo's existing iteration-test fixtures (`_FakeDispatchPlugin`, the `resolve_str` monkeypatch) — these are marked "*fill from test_ensemble.py*", not left as silent TODOs. The implementer must port those fixtures; flagged here so it isn't mistaken for complete.

**Type consistency:** `ForeachDirectives(concurrency, on_error)` is used identically in M2/M3; `substitute_env_vars(text, env)` signature is stable across M1.1/M1.2; the reducer payload is a JSON **array** in M4 and the script in M6.2 accepts a bare list (contract aligned in the M6.2 note).

**Known risk to confirm during implementation:** M5's claim that a `(binding, call)` list returns only the call's result depends on `_resolve_list`'s non-binding-join behavior — the M5 test exists specifically to verify/repair this.

## Scope note

This is one plan spanning the url4-executor + python_runner + config because the milestones are tightly coupled toward a single runnable query, but **each milestone lands independently** (its own tests + commit + PR) and advances a specific SF-34 subtask. If you prefer, M1–M3 (executor primitives) and M4–M7 (the scored pipeline) can be split into two PRs/plans.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-01-url4-scored-ensemble-query.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task with two-stage review between tasks (uses superpowers:subagent-driven-development).
2. **Inline Execution** — execute tasks in this session with checkpoints (uses superpowers:executing-plans).

**But first:** this plan is for your review. Please confirm the **Decision points (D1–D5)** and **Prerequisites (P1–P2)** — especially the dataset (`DATASET_URL` + field name) and whether v1 may drop the `normalized:`/validate layer — before any implementation begins.
