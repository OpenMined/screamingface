# Frontend Resolve: "Blocking and Screaming" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Rework the claude-frontend url4 spec resolution so it **blocks** on `/ensemble` (up to `resolve_timeout`, default raised to **1200s**) and, on any failure (TimeoutError, `/ensemble` 502, or a degraded `on_error=collect` 200), **surfaces a visible error to the CLI** via `_build_error_response` — never a silent context-less passthrough.

**Architecture:** This reverses PR #244 (SF-237)'s non-blocking + background-warm + silent direction, while **keeping** its two good parts: the **negative cache** (a failed spec fails-fast — re-raises the cached error within the TTL instead of re-running the ensemble) and the **bounded/loop-aware `_fetch_sync`** (no thread leak, cancels on timeout). The `$prompt` path already screams; we only unify its timeout. Branch: this lands on `SF-237-nonblocking-url4-resolve` (updates PR #244) — retitle the PR to "fail-loud".

**Tech Stack:** Python, FastAPI/Starlette proxy, httpx, `frontend_base.FrontendPluginBase`, pytest. Test via `cd apps/server && uv run pytest <path> -v`; pre-commit (ruff 0.9.0 + pyright) before push.

---

## Behavior matrix (target)

| Outcome of `/ensemble` resolve | Today (#244) | Target ("blocking + screaming") |
|---|---|---|
| Times out (`resolve_timeout`) | background, swallowed → no context, silent | block, then **`_build_error_response`** in CLI |
| `/ensemble` 502 (`on_error=abort`) | swallowed → silent | **`_build_error_response`** in CLI |
| Degraded 200 (`on_error=collect`, errors collected) | injected as context (garbage) | treated as failure → **scream** (best-effort, see Task 4) |
| Success | inject context | inject context (unchanged) |
| Repeat within `resolve_failure_ttl` after a failure | warm again / swallow | **re-raise cached error immediately** (fail-fast, no re-run) |

## File structure

| Path | Change |
|---|---|
| `apps/server/src/screamingface/plugins/frontend_base/plugin_base.py` | `resolve_timeout` 300→1200; `resolve_context` re-raises on failure + raises cached error when neg-cached; **remove** `get_cached_context`/`_maybe_warm`/`_warm` + `_RESOLVE_POOL`; `_fetch` honors `resolve_timeout` |
| `apps/server/src/screamingface/plugins/claude_frontend/_url4_context.py` | `resolve_static_context` calls blocking `resolve_context()` again (its existing `except` now screams); unify `_resolve_expression` timeout to `resolve_timeout`; best-effort degraded-200 detection |
| `apps/server/src/screamingface/plugins/frontend_base/tests/test_resolve_cache.py` | drop warm/concurrency tests; keep+adapt neg-cache; add "failure propagates" |
| `apps/server/src/screamingface/plugins/claude_frontend/tests/*` | add "resolve failure → `_build_error_response`" |

## Tasks

### Task 1 — `resolve_context`: block, neg-cache, and re-raise (stop swallowing)
**Files:** `frontend_base/plugin_base.py`
- [ ] `FrontendSettingsBase.resolve_timeout` default `300.0` → `1200.0`.
- [ ] In `resolve_context`'s per-spec loop:
  - When a spec is **negative-cached and unexpired**, instead of `continue` (silent skip), **raise** a `RuntimeError(f"spec {name!r} resolution failed recently (cooldown {…}s)")` so the caller screams fast without re-running.
  - In the `except Exception as exc:` block: keep `self._neg_cache[name] = time.monotonic() + settings.resolve_failure_ttl` and `_mark_span_error(...)`, then **`raise`** (remove the "deliberately don't re-raise" comment + swallow). On success keep `self._neg_cache.pop(name, None)`.
- [ ] Test (extend `test_resolve_cache.py`): a `_fetch_sync` that raises → `resolve_context()` **raises** (not returns None); the spec is neg-cached; a second call within TTL raises **without** calling `_fetch_sync` again (assert call count 1); after TTL it retries.

### Task 2 — Remove the background-warm machinery
**Files:** `frontend_base/plugin_base.py`
- [ ] Delete `get_cached_context`, `_maybe_warm`, `_warm`, the `self._warming` field, and `_RESOLVE_POOL` (now unused — `_fetch_sync` never used it). Keep `self._neg_cache` and `self._cache`.
- [ ] Remove now-dead imports (`ThreadPoolExecutor`) if unused.
- [ ] Delete the warm/concurrency tests in `test_resolve_cache.py` (`test_concurrent_warms_*`, `get_cached_context` tests).

### Task 3 — `resolve_static_context`: block + scream
**Files:** `claude_frontend/_url4_context.py`
- [ ] Change `resolved_context = plugin.get_cached_context() if plugin else None` back to `plugin.resolve_context() if plugin else None`. The existing `except Exception as exc: return _build_error_response(...)` now catches the re-raised failure → the CLI shows `[url4 error] … Traceback`. (No other change needed for timeout/502 screaming.)
- [ ] Test (`claude_frontend/tests/`): with a plugin whose `resolve_context` raises `TimeoutError`, `resolve_static_context(...)` returns a `JSONResponse` status 200 whose text contains `[url4 error]` and the exception class.

### Task 4 — Degraded-200 = failure (best-effort)
**Files:** `claude_frontend/_url4_context.py` (and/or `_fetch`)
- [ ] If the `/ensemble` response carries `X-SF-Collected-Errors` (header from #243) with a value > 0, treat the resolve as failed and scream. Since #243 may not be merged into this branch, guard it: only act if the header is present. If absent, no degraded detection (document as a follow-up that depends on #243). Do **not** parse the JSON body for `n_errors` here (couples the frontend to the scoring script shape) — prefer the header.
- [ ] Note in the PR body: full degraded-200 screaming lands once #243 (the `X-SF-Collected-Errors` header) merges.

### Task 5 — Unify the `$prompt` path timeout
**Files:** `claude_frontend/_url4_context.py` (`_resolve_expression`)
- [ ] Remote branch: replace `httpx.Timeout(300.0)` with `httpx.Timeout(settings_resolve_timeout)` (thread the resolve_timeout in; `resolve_prompt_expression` has `settings`). 
- [ ] In-process branch (`interpreter.evaluate(expression)`): wrap in `asyncio.wait_for(interpreter.evaluate(expression), resolve_timeout)` so it can't hang unboundedly. On `asyncio.TimeoutError`, let it propagate — `resolve_prompt_expression` already returns `_build_error_response` (it already screams). 
- [ ] Test: `_resolve_expression` in-process that exceeds a tiny timeout → raises → `resolve_prompt_expression` returns a `_build_error_response`.

### Task 6 — `_fetch` honors `resolve_timeout`
**Files:** `frontend_base/plugin_base.py`
- [ ] `_fetch(base_url, expression, timeout)` uses `httpx.AsyncClient(timeout=timeout, …)` and `_fetch_sync` passes its `timeout` through (so the inner HTTP cap matches the 1200 budget, not a hardcoded 300). Keep the loop-aware `asyncio.wait_for(_fetch(...), timeout)` from #244.

### Task 7 — Gates + PR
- [ ] `cd apps/server && uv run pytest src/screamingface/plugins/frontend_base/ src/screamingface/plugins/claude_frontend/ src/screamingface/plugins/codex_frontend/ src/screamingface/plugins/gemini_frontend/ src/screamingface/plugins/ollama_frontend/ -q` — all green (the base change is shared; other frontends must still pass).
- [ ] `uv run pre-commit run --files <touched>` (ruff 0.9.0 + pyright); re-stage if reformatted.
- [ ] Commit; push to `SF-237-nonblocking-url4-resolve`; **retitle PR #244** to "fix(frontend): blocking + fail-loud url4 resolve (negative cache + bounded fetch) (SF-237)" and update the body to describe the new direction. Do NOT merge.

## Risks & decisions
- **CLI hang vs visibility:** blocking means the CLI waits up to `resolve_timeout` (or until backends 600s × serialization). That's the user's explicit choice ("blocking and screaming"). The negative cache caps the damage to one slow attempt per TTL; CC's own client timeout may fire first (then CC shows its own timeout — acceptable).
- **Other frontends (codex/ollama/gemini)** share `frontend_base`. They call `resolve_context()` synchronously already; making it re-raise means a resolve failure now screams for them too (their proxy paths must build an error response or the exception must be handled). Verify each frontend's proxy path surfaces or tolerates the raise; if a frontend has no `_build_error_response` equivalent, it must catch and degrade — confirm in Task 7's regression.
- **Degraded-200** full handling depends on #243's header (Task 4 best-effort).
