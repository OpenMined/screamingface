---
ticket: OME-926
stack: screamingface
status: done
started: 2026-08-21
finished: 2026-08-21
---

# OME-926 — one completion dispatcher for ConnectionPanel background work

## Intent

`sf.connect()` in Colab can remain forever on "checking". `ConnectionPanel` caches the
asyncio loop live at `widget()` time and posts every background completion back to *that*
loop via `call_soon_threadsafe`; when the notebook host has closed or replaced it, the call
raises `RuntimeError` which is swallowed with a bare `return`, so `access_check_pending`
never clears. Replace loop-identity dependence with one dispatcher that always runs the
completion, so Colab and Jupyter expose the same user-visible transitions.

FEATURE: hosted-Engine connection panel (`sf.connect()`).
STORY: as a Colab user, I run `sf.connect()` and reach Log in / provider rows / a readable
error — never a permanent "checking".

## Planned changes

- `packages/screamingface/src/screamingface/_ui/connections.py`
  - new `_dispatch(callback, *args)` helper: live loop resolved **at post time** →
    else cached `self._loop` if open → else run inline on the calling thread.
    INVARIANT: every path ends with the completion actually running.
  - route `_start_access_check_thread` (:309-336), `_start_login_thread` (:354-377) and
    `_auth_state_changed` (:395-404) through it; audit `_start_oauth` (:226-236) and keep
    its behaviour.
  - drop the silent `weakref` completion drop (:323-325).
  - `_repr_html_` (:146-152) must not render a stuck `checking` — it never starts the probe.
- `packages/screamingface/src/screamingface/_ui/connection_view.py` — stop rendering the
  "Checking…" button `disabled = True` (:242-245), so a hung probe stays recoverable.
- `packages/screamingface/tests/test_connection_panel.py` — tests (append-only).

Out of scope per the issue: Cloudflare auth, provider-connection contracts, other widgets.
`sf.connect()` stays non-blocking. No schema/model change, so S1 does not apply.

## Test plan

RED first, reusing `_panel`/`_text`/`_wait_for_button`/`_buttons` (:66-150) and
`_SharedAuthClient` (:110-149); styled after
`test_unexpected_login_failure_does_not_leave_panel_waiting` (:816-834). No prior test is
modified.

- **Regression guard:** render the real controller, close/replace the rendering loop before
  Access discovery completes, assert the panel leaves "checking".
- Access-required / unprotected-Engine / discovery-**error** each reach the right terminal
  state (the error path is currently untested).
- Login completion cannot remain on "Cancel" solely because the rendering loop changed.
- Module-level `sf.connect()` entrypoint (`_default_client.py:121-171`), not just the
  internal helper — explicitly required by the issue's acceptance.
- `_repr_html_` while `access_check_pending` does not render a stuck `checking`.
- Existing Jupyter connection + OAuth tests stay green and unmodified.

Baseline before this unit: `Checking…`, `checking`, `access_check_pending`,
`_start_access_check`, `_complete_access_check` appear **nowhere** in `tests/`.

## Acceptance

- The regression guard fails before the fix and passes after.
- All six issue acceptance bullets covered by a test.
- `uv run .claude/scripts/run_gates.py screamingface` green, including
  `--cov-fail-under=95`, the notebook determinism check, and the distribution check.

## Outcome

- **Actual files:**
  - NEW `src/screamingface/_ui/loop_dispatch.py` (80) — `_CompletionDispatcher`. Planned as
    an inline `_dispatch` helper; extracted on owner approval because the inline version
    pushed `connections.py` to 485 lines against the loop's ≤450 rule (it was already 454
    on `origin/main`). Now 439.
  - `src/screamingface/_ui/connections.py` — three call sites routed through the
    dispatcher; both `except RuntimeError: return` swallows deleted; the dead `loop`
    parameter dropped from both thread starters; `_start_access_check` re-renders after
    marking the probe started.
  - `src/screamingface/_ui/connection_state.py` — `checking` requires
    `access_check_pending AND access_check_started`.
  - `tests/test_connection_panel.py` — 8 tests added (+1 prior test retargeted, below).
  - `src/screamingface/_runtime/server.py` — unplanned, owner-approved: see Deviations.

- **Commits:** see PR.

- **Gates:** `run_gates.py screamingface --skip-append-only` — ALL GATES GREEN.
  1017 passed, 1 skipped; coverage 95.40% (gate 95%). ruff · ruff format · pyright ·
  notebook determinism · `uv build` · distribution check all green.

- **Deviations:**
  1. **Dispatcher extracted to its own module** rather than inlined — owner-approved, to
     satisfy the ≤450-line rule. Gives the issue's "one completion-dispatch mechanism" a
     named home.
  2. **One prior test modified** — `panel._loop = stale_loop` →
     `panel._dispatcher.adopt(stale_loop)` in the OAuth live-loop test (~:363). Injection
     handle only; scenario and every assertion unchanged, still passing. Raised as a rule-5
     Confidence-Gate decision and approved before editing. Gates therefore run with
     `--skip-append-only`, the runner's documented path.
  3. **`_runtime/server.py:177` typed `app: Any`** — unrelated to OME-926 and outside the
     issue's scope, fixed here on owner approval. `app: object` typechecked only while
     uvicorn was absent; CI installs `--extra notebook` (uvicorn lives in `runtime`) so CI
     never saw it, while the local gate runner installs uvicorn and failed on clean
     `origin/main`. A local gate red on main trains people to ignore it, so it was worth
     clearing. **Latent gate-fidelity gap remains: the local runner and CI do not install
     the same extras.** Worth its own issue.
  4. **Retry affordance NOT implemented.** The plan floated making the disabled "Checking…"
     button clickable. Dropped: the issue's acceptance is scoped to completions that have
     *finished* ("never remain pending after the background operation has completed"), which
     the dispatcher fully satisfies. A genuinely hung probe is a different defect, and a
     live button needs retry machinery nothing yet demands (YAGNI). `disabled = True` stands.
  5. **`weakref` completion drop left alone.** The plan listed removing it; on reading, a
     GC'd or `_closed` panel has nothing to render, so returning there is correct. Only the
     `RuntimeError` path was the bug.

- **Not reproduced locally in Colab.** The regression guard reproduces the reported state
  deterministically (render on a loop, close it, then release the probe), which is what the
  issue's acceptance asks for. A real Colab pass is still worth doing — see Owner-verify.

- **Latent, unfixed (flagged per plan):** `AsyncClient._access_required` is `async def`
  (`client.py:473-475`) but `_start_access_check` only checks `callable(...)`, so a coroutine
  would read truthy ⇒ "access required", never awaited. Unreachable today —
  `ConnectionPanel` is only built from the sync `Client` (`client.py:288-294`).
