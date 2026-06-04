# Demo-path Silent Failures — Diagnostic & Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each work item task-by-task. Steps use checkbox (`- [ ]`) syntax. **Each work item is an independent branch/PR — do not bundle them into one PR.**

**Goal:** Fix the cluster of silent-failure defects on the URL4 → /ensemble → scoring → persistence → proxy demo path that today let a broken run look green, hang the CLI for ~26 min, mislabel a utility backend as "credential missing", and leave Eval Studio empty.

**Architecture:** Five independent defects across five server plugins (`url4_executor`, `llm_base`, `frontend_base`/`claude_frontend`, `eval_runs`, `python_runner`). This document is one diagnostic + a set of separately-shippable fixes (one branch/PR each). They share no code changes, so they can land in any order; a recommended sequence is in Part D.

**Tech Stack:** Python 3.12, FastAPI + Starlette, Tortoise ORM + SQLite, `tatsu` URL4 grammar, OpenTelemetry + Phoenix tracing, httpx, pytest (`asyncio_mode=auto`), uv, ruff 0.9.0 (pinned), pyright.

---

## Part A — Diagnostic (evidence)

All five were observed live on **2026-06-04** while investigating trace `1652633c3d503c90113d65b84a34ac39` (a `ScoredLiveTruth` run) plus the state DB at `~/.screamingface/state.db`.

| # | Defect | Evidence | Root cause (file:line) |
|---|--------|----------|------------------------|
| **4** | Per-row `check_correct` intent JSON breaks on un-escaped model output | Span `dfe52eda…` = `ERROR`: `intent is not valid JSON: Invalid control character at … char 348` at `python_runner/plugin.py:140`. A model answer contained a raw newline that was substituted unescaped into `{"…":"$consensus",…}`. | Raw string substitution into a `json_blob` intent: `ensemble_helpers.py:215` (`substitute_item`) and `:148` (`substitute_env_vars`) insert values without JSON-escaping. |
| **2** | `;foreach.on_error=collect` makes failures invisible | Root `GET /ensemble` = `UNSET` / HTTP 200 with `{"accuracy_pct":37.5}` while one row's subtree is `ERROR`. `calculate_accuracy` drops error rows from the denominator → accuracy silently biased. | `ensemble.py:235-246` converts row exceptions to error elements but sets no error count on the span / response; `routes.py` returns 200. |
| **3** | Proxy resolve hangs the CLI for ~26 min | Phoenix: run took **324.5s**; claude-frontend (`resolve_timeout=300`) gave up at 300s. Result discarded, not cached; `resolve_context` holds `self._lock`; every request re-runs the 5-min ensemble serially. | `frontend_base/plugin_base.py:242-336` (`resolve_context`/`_fetch_sync`) — blocking, no negative cache, no cancellation; called on the hot path at `claude_frontend/_url4_context.py:resolve_static_context`. |
| **1** | `/python` shows "Credential is missing or expired" | `python-runner` declares `backend_call_paths=["/python"]` but has no `/python/health` → 404 → classified `reauth`. | `llm_base/routes.py:66-87` (`_collect_backend_status`) sweeps **every** plugin with `backend_call_paths`, not just credentialed ones. |
| **5** | Eval Studio empty despite "successful" ensemble output | DB: `eval_run`=4 rows (all `failed`, newest yesterday), `eval_question`=0 ever. The successful output came from the proxy resolve path, which sends no run headers. | **By design** (`routes.py:101` gates persistence on `X-SF-Run-Id`/`X-SF-Run-Spec`). The real gap is that header-path runs all fail — a downstream symptom of #4/#2. |

**Key cross-cutting insight:** #5 is not a code bug in the proxy. Eval Studio is empty because (a) proxy-resolved ensembles correctly don't persist, and (b) the only runs that *do* go through the header path (desktop RunView) fail — because of #4 (rows error before `check_correct`, so `HOOK_QUESTION_CHECKED` never fires → 0 `eval_question` rows) and the failure is masked by #2. **Fixing #4 + #2 is what makes Eval Studio populate.**

---

## Part B — Shared context: test & CI gates (apply to every work item)

These are `apps/server` changes, so CI **does** gate them (unlike desktop).

- **Run a test:** `cd apps/server && uv run pytest <path> -v`
- **Unit suite:** `cd apps/server && uv run pytest -m "not e2e and not e2e_live" -v` (CI runs this with `--cov=screamingface`, **70% coverage gate**, via `.github/workflows/server-tests.yml`).
- **E2E suite:** `cd apps/server && uv run pytest tests/e2e/ -m "e2e" -v` (CI runs with `--timeout=120`).
- **Markers** (`apps/server/pyproject.toml`): `e2e` (subprocess server), `e2e_live` (real Anthropic key). `testpaths = ["tests", "src/screamingface/plugins"]`, `asyncio_mode = "auto"`.
- **Pre-commit (CI `.github/workflows/pre-commit.yml`, paths-filtered to `apps/server/**`):** ruff `--fix` → ruff-format → pyright. **ruff is pinned to v0.9.0** while local ruff differs — after `pre-commit run`, if ruff-format reformats, **re-stage and re-commit**. Run before pushing:
  ```bash
  cd apps/server && uv run pre-commit run --files <changed files>   # then git add the reformatted files
  ```
- **Per-plugin test dirs:** `src/screamingface/plugins/<plugin>/tests/`. E2E tests live in `apps/server/tests/e2e/`.
- **Branching (every WI):** `git fetch origin && git checkout -b <SF-NNN>-<slug> origin/main`. Open a PR and stop — **do not merge** (the user reviews/merges). Branch names lead with the SF ticket id; create the Asana ticket first (see Part D).

---

## Part C — Work items

### WI-1 — URL4 intent JSON-escaping  *(Defect #4 — highest priority; unblocks the demo + Eval Studio)*

**Problem:** `$item.field` and `$consensus` are substituted as raw text into a `json_blob` intent (`{"consensus":"$consensus",…}`). A model answer with a newline/tab/quote produces invalid JSON → the whole row fails at `python_runner/plugin.py:140`.

**Design decision (recommended approach):** Escape a substituted value **only when its token sits inside a `{...}` json_blob span**, leaving non-JSON positions (e.g. `/claude($item.question)`) untouched. This is JSON-context-aware, needs **no grammar/AST change**, and fixes both substitution functions uniformly. (The naive "escape every string" approach is rejected — it would corrupt plain-text/backend-context positions; see Risks.)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble_helpers.py` (add helpers; update `substitute_item` ~194-226 and `substitute_env_vars` ~128-150)
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_intent_json_escaping.py` (new)

- [ ] **Step 1 — Write the failing test.** Create `tests/test_intent_json_escaping.py`:
```python
import json

from screamingface.plugins.url4_executor.ensemble_helpers import (
    substitute_env_vars,
    substitute_item,
)
from screamingface.plugins.url4_executor.interpreter import Env  # adjust import to where Env lives


def test_item_field_with_newline_stays_valid_json_inside_blob():
    template = '/python(/data/code/check_correct.py)!{"q":"$item.question"}'
    item = json.dumps({"question": "line1\nline2\twith\ttabs and \"quotes\""})
    out = substitute_item(template, item)
    blob = out.split("!", 1)[1]
    assert json.loads(blob)["q"] == "line1\nline2\twith\ttabs and \"quotes\""


def test_item_field_outside_blob_is_not_escaped():
    template = "/claude($item.question)"
    item = json.dumps({"question": "what is 2\n+2?"})
    out = substitute_item(template, item)
    # backend-context position: value inserted raw (no backslash-n)
    assert out == "/claude(what is 2\n+2?)"


def test_env_var_with_control_char_escaped_inside_blob():
    env = Env.root().child(consensus="A\nB")
    text = '{"consensus":"$consensus"}'
    out = substitute_env_vars(text, env)
    assert json.loads(out)["consensus"] == "A\nB"


def test_env_var_outside_blob_not_escaped():
    env = Env.root().child(name="x\ny")
    assert substitute_env_vars("hello $name", env) == "hello x\ny"
```
- [ ] **Step 2 — Run, verify it fails.** `cd apps/server && uv run pytest src/screamingface/plugins/url4_executor/tests/test_intent_json_escaping.py -v` → FAIL (`json.loads` raises / unescaped output).
- [ ] **Step 3 — Implement.** At the top of `ensemble_helpers.py` (near the other imports/regexes) add:
```python
# Mirrors the json_blob grammar atom (url4_grammar.py): a balanced {...}
# allowing one level of nesting. Substituted values that land INSIDE such a
# span must be JSON-escaped so control chars/quotes in model output don't
# break json.loads downstream (python-runner).
_JSON_BLOB_RE = re.compile(r"\{(?:[^{}]|\{[^{}]*\})*\}")


def _json_blob_spans(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in _JSON_BLOB_RE.finditer(text)]


def _in_json_blob(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def _escape_for_json_string(s: str) -> str:
    """Escape a plain string for safe insertion inside a JSON string literal.

    ``json.dumps("a\\nb")`` -> ``'"a\\nb"'``; strip the surrounding quotes so the
    result drops into an existing ``"..."`` position.
    """
    return json.dumps(s)[1:-1]
```
  Then in `substitute_item`, compute spans once and escape `$item.field` string values inside a blob:
```python
def substitute_item(template: str, item_json: str) -> str:
    field_pattern = re.compile(r"\$item\.([a-zA-Z_][a-zA-Z0-9_]*)")
    blob_spans = _json_blob_spans(template)
    parsed_item: dict | None = None

    def _field_replacer(match: re.Match) -> str:
        nonlocal parsed_item
        if parsed_item is None:
            try:
                parsed_item = json.loads(item_json)
            except (json.JSONDecodeError, TypeError):
                parsed_item = {}
        field = match.group(1)
        if isinstance(parsed_item, dict) and field in parsed_item:
            val = parsed_item[field]
            if isinstance(val, str):
                return (
                    _escape_for_json_string(val)
                    if _in_json_blob(match.start(), blob_spans)
                    else val
                )
            return json.dumps(val)  # non-strings are already valid JSON tokens
        return match.group(0)  # unknown field — leave as-is

    result = field_pattern.sub(_field_replacer, template)
    bare_pattern = re.compile(r"\$item(?!\.[a-zA-Z_])")
    return bare_pattern.sub(lambda _match: item_json, result)
```
  And in `substitute_env_vars`, escape `$name` string values inside a blob:
```python
def substitute_env_vars(text: str, env: "Env | None") -> str:
    if not text or env is None or "$" not in text:
        return text
    token = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")
    blob_spans = _json_blob_spans(text)

    def _replace(m: re.Match) -> str:
        name = m.group(1)
        if name == "item":
            return m.group(0)
        try:
            value = env.lookup(name)
        except KeyError:
            return m.group(0)
        val_str = value if isinstance(value, str) else str(value)
        return (
            _escape_for_json_string(val_str)
            if _in_json_blob(m.start(), blob_spans)
            else val_str
        )

    return token.sub(_replace, text)
```
- [ ] **Step 4 — Run, verify it passes.** Same command as Step 2 → PASS.
- [ ] **Step 5 — Regression sweep.** `cd apps/server && uv run pytest src/screamingface/plugins/url4_executor/ -q` (covers existing fan-out/collection tests). Expected: all pass.
- [ ] **Step 6 — Pre-commit + commit.** `uv run pre-commit run --files src/screamingface/plugins/url4_executor/ensemble_helpers.py src/screamingface/plugins/url4_executor/tests/test_intent_json_escaping.py`; re-stage if reformatted; `git commit -m "fix(url4): JSON-escape \$item/\$var substitutions inside json_blob intents"`.

**Acceptance:** a model answer containing a newline/tab/quote yields a valid `check_correct` intent; the row succeeds; positions outside `{...}` are unchanged.

---

### WI-2 — Make collected errors visible  *(Defect #2)*

**Problem:** under `on_error=collect`, row failures are swallowed; the run reports 200/"done" and accuracy is silently biased (error rows excluded from the denominator). Even after WI-1, genuine row failures must not be invisible.

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/ensemble.py` (the `on_error=="collect"` branch ~235-246; collection-iterate span ~212-262)
- Modify: `apps/server/src/screamingface/plugins/url4_executor/routes.py` (response construction ~121-164)
- Test: `apps/server/src/screamingface/plugins/url4_executor/tests/test_collected_errors_visible.py` (new)

- [ ] **Step 1 — Failing test** (assert the count is tracked + surfaced). Create the test using the in-process app + `httpx.ASGITransport` pattern from `eval_runs/tests/test_e2e_persistence.py`, with a fake backend that raises on one of N items, asserting the response carries `X-SF-Collected-Errors: 1`. (Mirror the fake-plugin injection used in `test_scored_query.py`.)
- [ ] **Step 2 — Run, verify it fails** (header absent today).
- [ ] **Step 3 — Implement.** In `ensemble.py`, count errors in the collect branch and stash on the interpreter + span:
```python
if directives.on_error == "collect":
    raw = await asyncio.gather(*[_guarded(i) for i in items], return_exceptions=True)
    results = []
    error_count = 0
    for r in raw:
        if isinstance(r, BaseException):
            error_count += 1
            results.append(json.dumps({"error": {"kind": type(r).__name__, "message": str(r)}}))
        else:
            results.append(r)
    self._last_collected_errors += error_count          # instance counter, reset per evaluate()
    set_span_attrs({"url4.collection.errors_collected": error_count})
else:
    results = list(await asyncio.gather(*[_guarded(i) for i in items]))
set_span_attrs({"url4.collection.result_count": len(results)})
return results
```
  Initialize `self._last_collected_errors = 0` at the start of `evaluate()` (so it reflects the current request, not a span readback). In `routes.py`, surface it on the response:
```python
result = await interpreter.evaluate(q, env=env)
...
response = PlainTextResponse(content=result) if not ast else JSONResponse(...)
if getattr(interpreter, "_last_collected_errors", 0):
    response.headers["X-SF-Collected-Errors"] = str(interpreter._last_collected_errors)
return response
```
- [ ] **Step 4 — Run, verify it passes.**
- [ ] **Step 5 (recommended add-on) — persist error rows for eval runs.** When a row fails *under a `__run_id__`*, emit `HOOK_QUESTION_CHECKED` with `correct=False, error=<msg>` so `eval_question` reflects failures and the accuracy denominator is honest (today the hook only fires on `check_correct` success, so failed rows vanish from Eval Studio). Capture the row's `$item` context at the `on_error=collect` catch site and emit the hook there (guard on `env.lookup("__run_id__")`). Add a test in `eval_runs/tests/` asserting a failing row produces an `eval_question` with `correct=False`.
- [ ] **Step 6 — Pre-commit + commit** (`fix(url4): surface on_error=collect failures via X-SF-Collected-Errors + span attr`).

**Acceptance:** a run with K collected errors returns `X-SF-Collected-Errors: K`, sets `url4.collection.errors_collected` on the span, and (with Step 5) records failed rows in `eval_question`.

**Open decision:** keep HTTP 200 (collect stays "robust") vs. switch to `206 Partial Content` when errors>0. Recommend **200 + header** (non-breaking); flag 206 as a follow-up if monitoring needs a status-code signal.

---

### WI-3 — Proxy resolve must not hang the CLI  *(Defect #3)*

**Problem:** `resolve_context` blocks the proxied chat for up to `resolve_timeout=300s`, discards the (late, 324s) result, never negative-caches, and serializes on `self._lock` → ~26-min CLI hangs and a leaked daemon thread + server run per attempt.

**Files:**
- Modify: `apps/server/src/screamingface/plugins/frontend_base/plugin_base.py` (`__init__` cache fields; `resolve_context` ~242-297; `_fetch_sync` ~310-336)
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/_url4_context.py` (`resolve_static_context`)
- Test: `apps/server/src/screamingface/plugins/frontend_base/tests/test_resolve_cache.py` (new)

- [ ] **Step 1 — Failing tests:** (a) a failing `_fetch_sync` is negative-cached for the TTL so the *second* `resolve_context` does **not** re-fetch; (b) `resolve_static_context` returns/continues without blocking when resolution isn't ready. Inject a fake `_fetch_sync` that counts calls / sleeps.
- [ ] **Step 2 — Run, verify they fail** (today it re-fetches every call).
- [ ] **Step 3 — Implement (priority order):**
  1. **Negative cache (short TTL).** Add `self._neg_cache: dict[str, float] = {}` and a `resolve_failure_ttl: float = 60.0` setting. On the `except` at ~279, record `self._neg_cache[name] = <monotonic now> + ttl`. At the top of the per-spec loop, if `name` is in `_neg_cache` and not expired, skip (treat as unresolved) without calling `_fetch_sync`. Use `time.monotonic()` (pass it in or use a small helper — note: workflow-time restrictions don't apply to runtime code).
  2. **Bounded, cancellable fetch.** Replace the raw daemon `Thread` with a module-level `ThreadPoolExecutor(max_workers=2)` and `future.result(timeout=timeout)`; on `FutureTimeoutError`, `future.cancel()` and raise `TimeoutError`. This bounds thread growth and stops leaking one thread per timeout. (Cancelling the in-flight httpx request fully also requires the fetch to observe cancellation; at minimum the bounded pool caps the leak.)
  3. **Off the hot path.** In `resolve_static_context`, treat resolution as best-effort: if cached context exists, inject it; otherwise inject nothing and **return immediately** (never block the chat). Trigger a background warm (e.g., schedule `resolve_context` on a worker) so the cache fills without delaying any request.
  4. **Confirm the non-fatal fallback** still returns `None`/continues when context is absent (it does at ~294 / call site) — the fix removes the *blocking*, the fallback was already correct.
- [ ] **Step 4 — Run, verify passes.**
- [ ] **Step 5 — Pre-commit + commit** (`fix(frontend): negative-cache + non-blocking url4 resolve so slow evals never hang the CLI`).

**Acceptance:** with `/ensemble` stalling past the timeout, the proxied chat returns promptly (no context), repeated requests do not each re-run the ensemble, and no unbounded `url4-fetch` threads accumulate.

**Open decision:** also raise `resolve_timeout` (e.g. 600s) — only meaningful *combined* with off-hot-path warming; alone it just delays the hang. Recommend keeping 300s + warming.

---

### WI-4 — Backend-status sweep skips utility backends  *(Defect #1)*

**Problem:** `_collect_backend_status` probes every plugin with `backend_call_paths`, so `python-runner` (no auth, no `/python/health`) is shown as "Credential is missing or expired."

**Files:**
- Modify: `apps/server/src/screamingface/plugins/llm_base/routes.py` (`_collect_backend_status` ~66-87)
- Test: `apps/server/src/screamingface/plugins/llm_base/tests/test_backends_status_v2.py` (extend)

- [ ] **Step 1 — Failing test:** register a fake plugin with `backend_call_paths=["/python"]` and neither `gateway_provider` nor `cli_auth_command`; assert it is **absent** from `_collect_backend_status` output, while a fake with `cli_auth_command` is present.
- [ ] **Step 2 — Run, verify it fails** (python appears today).
- [ ] **Step 3 — Implement** — one guard, keyed off the same discriminators the rest of the file already uses:
```python
for plugin in plugins.values():
    if not plugin.backend_call_paths:
        continue
    # Only credentialed LLM backends belong in the auth/status sweep. A utility
    # backend (e.g. python-runner) has neither a gateway provider nor a CLI auth
    # command, so probing it for credentials is meaningless.
    if not (getattr(plugin, "gateway_provider", None) or getattr(plugin, "cli_auth_command", None)):
        continue
    ...
```
- [ ] **Step 4 — Run, verify it passes**; then `uv run pytest src/screamingface/plugins/llm_base/tests/ -q`.
- [ ] **Step 5 — Pre-commit + commit** (`fix(llm-base): exclude non-credentialed backends from /backends/status sweep`).

**Acceptance:** `/python` no longer appears in `/backends/status`; all real LLM backends (all `aigw-*` via `gateway_provider`, CLI backends via `cli_auth_command`) are unchanged.

---

### WI-5 — Eval Studio population: verify, don't code  *(Defect #5)*

**No proxy code change** — proxy-resolved ensembles correctly don't persist (they send no run headers; only desktop RunView does). This item is verification that WI-1 + WI-2 actually make header-path runs persist.

- [ ] After WI-1 (and ideally WI-2 Step 5) merge, start a run from the desktop **RunView** (which sends `X-SF-Run-Id`/`X-SF-Run-Spec`) against `ScoredLiveTruth`.
- [ ] Confirm in `~/.screamingface/state.db`: a new `eval_run` row with `status=done`, non-null `accuracy`, `total_questions>0`, and matching `eval_question` rows (`SELECT status, accuracy, total_questions FROM eval_run ORDER BY created_at DESC LIMIT 1;`).
- [ ] Confirm Eval Studio shows the new row.
- [ ] If still failing: capture the new failing trace/span and the `HOOK_RUN_FAILED` `error`, and reopen — the remaining failure is a *new* root cause, not #5.

**Acceptance:** one green `eval_run` with persisted questions appears end-to-end from RunView. (Documents that the historical 4 `failed`/0-question rows were caused by #4.)

---

## Part D — Sequencing & ticket mapping

**Recommended order** (by demo impact):
1. **WI-1** (intent escaping) — without it, real runs fail and Eval Studio stays empty.
2. **WI-2** (error visibility) — so any remaining failures are loud, not silent.
3. **WI-3** (proxy hang) — stops the 26-min CLI freeze.
4. **WI-4** (status badge) — cosmetic, independent.
5. **WI-5** (verify) — after 1+2.

**Tickets/branches:** create one Asana ticket per WI (the user's convention leads branch names with `SF-NNN`). Suggested:
- `SF-NNN  fix: URL4 intent JSON-escaping`  → branch `SF-NNN-url4-intent-json-escaping`
- `SF-NNN  fix: surface on_error=collect failures`
- `SF-NNN  fix: non-blocking proxy url4 resolve`
- `SF-NNN  fix: status sweep skips utility backends`
- (WI-5 folds into WI-1's ticket as a verification task, or its own.)

Each: branch from fresh `origin/main`, open a PR, **stop for review** (no auto-merge, no force-push).

---

## Part E — Risks & open decisions

1. **WI-1 escaping scope (the one real design call).** Escape **only inside `{...}` spans** (recommended). The rejected alternative — escape every substituted string — would corrupt non-JSON positions (e.g. the prompt in `/claude($item.question)` would gain visible `\n`). The span approach computes positions on the original template, so `re.sub` match offsets align. Edge: bare `$item` (whole object) inside a blob string position is unusual and left raw; document it.
2. **WI-1 double-escaping.** Values must be **plain** strings, not pre-escaped JSON. Within one substitution pass this holds; do not chain two escaping passes over the same blob.
3. **WI-2 status semantics.** 200 + header vs 206. Recommend 200 + header (non-breaking). Eval-run accuracy honesty depends on WI-2 Step 5 (persisting failed rows); without it, accuracy is computed only over *graded* rows.
4. **WI-3 negative-cache staleness.** A 60s TTL can briefly serve a stale "failed" state after a transient blip. Make TTL configurable; log clearly. Cancelling the in-flight httpx request fully (not just bounding the pool) requires the fetch to observe cancellation — bounded `ThreadPoolExecutor` caps the leak even if full cancellation is deferred.
5. **WI-4 over-exclusion.** A *real* LLM backend missing both `gateway_provider` and `cli_auth_command` would now be excluded — but such a plugin has no auth method and shouldn't be in the sweep anyway. Verify no current backend is in that state (all `aigw-*` set `gateway_provider`; `claude_backend_api` sets `cli_auth_command`).
6. **CI/ruff pin.** Local ruff ≠ pinned 0.9.0. Always `pre-commit run` and re-stage reformatted files before pushing, or CI pre-commit fails. Server-tests CI enforces a 70% coverage gate — keep the new tests meaningful.
7. **`Env` import paths** in test stubs (WI-1) — confirm the actual module for `Env` (`interpreter.py` vs `env.py`) before writing the test import.
