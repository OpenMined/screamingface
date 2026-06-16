# Design Spec — Detect & surface backend-unavailable in eval runs

- **Ticket:** SF-270 — https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215654793910878
- **Date:** 2026-06-12
- **Status:** Design (approved decisions baked in) → implementation plan alongside

## Context

ScoredLiveTruth (and any spec that calls a model backend) **silently produces zero scored records when a backend is unavailable**. Root cause (confirmed):

- Each row scores via `consensus=/claude($item.question)!…`. When the Claude backend is down, every `/claude` call fails.
- The spec runs with `;foreach.on_error=collect`, which is deliberately robust: it collects per-row failures, keeps **HTTP 200**, and the run is marked **`done`** (never `failed`).
- `check_correct` gets no real consensus → no verdict; `calculate_accuracy` excludes the error rows → `n=0, accuracy 0%, errors=N`.
- The eval run is recorded as `done` with **zero graded records**, and nothing tells the user the backend was down. The existing `X-SF-Collected-Errors` response header (SF-236) is ignored by the fire-and-forget run starter and never persisted/shown.

**Goal:** (1) **preflight** — before starting a run, warn the user if a backend the spec references is unavailable; (2) **degraded status** — after a run, if rows were collected as errors, persist the count and mark the run `degraded` with a reason, surfaced in Eval Studio. Detection covers **any backend the spec references** (decisions locked with the user).

## Scope

**In:** `apps/server` (url4_executor, eval_runs) + `apps/desktop` (Eval Studio run flow + display). Backends in scope: any `/claude`, `/codex`, `/gemini`, `/ollama` the expression references.

**Out:** changing `on_error=collect` semantics (kept robust); ret`/`auto-retry of failed runs; non-eval url4 traffic (live frontend requests don't create eval records); web portal.

## Key facts (from code research)

- **Backend health source of truth:** `GET /backends/status` (v2) — `llm_base/routes.py`. Per-backend verdict via `_classify_action` → `healthy | reauth | rate_limited | degraded`, plus `authenticated: bool`. The walk already skips `requires_auth=False` runners (python). Backends are keyed by name = `backend_call_paths[0].lstrip("/")` (`claude`/`codex`/`gemini`/`ollama`).
- **Desktop already polls it:** `use-backend-status.ts` → `useBackendStatus()` returns `{ statuses, refresh }`; `isBackendStatusV2(statuses)` then `statuses.backends[name].authenticated`/`.action`. No new server call needed for preflight.
- **Run start funnel:** `EvalStudioView.tsx::runAndSelect` is the single path for all three start entry points (runs list, run detail, add dialog) → `useStartEvalRun()` → `GET /ensemble?q=…` with `X-SF-Run-Id`/`X-SF-Run-Spec`.
- **Collected errors available pre-persist:** in `url4_executor/routes.py`, `interpreter._collected_errors` is computed before the `HOOK_RUN_FINISHED` emit; it's only read *after* today (for the header). It can be passed into the emit.
- **Run model:** `EvalRun.status` is `CharField(max_length=16)` with `running|done|failed`; `"degraded"` fits. Already has `error: TextField`, `accuracy`, `total_questions`, `correct_questions`. `_on_run_finished`/`_on_run_failed` in `eval_runs/plugin.py` set status; `RunFinishedPayload` in `_hook_payloads.py` carries only `run_id`+`finished_at` today.
- **Desktop display:** `EvalRunDetail.tsx` shows `<EvalStatusBadge status=…/>` + an `error` block; `EvalRunStatus = 'running'|'done'|'failed'` and `EvalStatusBadge` styles those three — both need a `degraded` entry. The client already carries `error` end-to-end.

## Design

### 1. Referenced-backend extraction (shared helper)
A small pure helper maps a url4 expression → the set of auth-requiring backend names it calls, by scanning for the backend-call tokens `/claude`, `/codex`, `/gemini`, `/ollama` (the `requires_auth` providers; `/python`, `/data`, `/private` excluded). Implemented on the desktop (for preflight) as `lib/referenced-backends.ts`. Regex on call-paths is sufficient and matches how the server keys backends.

### 2. Preflight (desktop, before run)
In `runAndSelect` (`EvalStudioView.tsx`): before calling `startEvalRun`, compute the referenced backends; `await refresh()` then read `useBackendStatus()`; if any referenced backend is **not authenticated/healthy**, show a confirm dialog (reuse `ConfirmDialog`): _"Claude backend is unavailable (needs auth). This run will produce no scored records. Start anyway?"_ — listing each unavailable backend + its `action`/`help_text`. **Proceed only on confirm**; "Cancel" aborts (no run created). If all healthy, run immediately (no dialog).

### 3. Degraded status (server, after run)
In `url4_executor/routes.py`: read `collected_errors = getattr(interpreter, "_collected_errors", 0)` **before** the `HOOK_RUN_FINISHED` emit and pass it in. Extend `RunFinishedPayload` with `collected_errors: int = 0`. In `eval_runs/plugin.py::_on_run_finished`: when `collected_errors > 0`, set `status="degraded"` and an `error` reason like `"{collected_errors} row(s) errored (e.g. backend unavailable); {graded} graded."` instead of `"done"`. Runs with no collected errors stay `done`. (Hard failures still go through `HOOK_RUN_FAILED` → `failed`.)

### 4. Degraded display (desktop)
Add `'degraded'` to `EvalRunStatus` (`components/eval/types.ts`) and a style entry in `EvalStatusBadge.tsx` (amber/mark — it's a warning, not a hard fail). The reason renders through the existing `EvalRunDetail` `error` block with no new wiring.

## Data flow

1. **Preflight:** user clicks Run → `runAndSelect` extracts referenced backends → `refresh()` + check `statuses` → if any unavailable, `ConfirmDialog`; cancel aborts, confirm proceeds.
2. **Run:** `GET /ensemble?q=…` with run headers → executor evaluates → `_collected_errors` tallied.
3. **Persist:** `HOOK_RUN_FINISHED(run_id, finished_at, collected_errors)` → `_on_run_finished` writes `status=degraded`+reason when `collected_errors>0`, else `done`.
4. **Display:** runs list/detail poll → `degraded` badge + reason in the error block.

## Testing

- **Server:** unit test `_on_run_finished` sets `degraded`+reason when `collected_errors>0`, `done` when 0. Route test: a resolve whose interpreter reports collected errors persists `degraded` (can stub the interpreter / use a small `on_error=collect` expression with a deliberately failing node).
- **Desktop:** unit test `referenced-backends.ts` (claude-only spec → {claude}; 3-way → {claude,codex,gemini}; `/python`/`/data` excluded). Component/logic test that `runAndSelect` aborts when a referenced backend is unauthenticated and the user cancels; proceeds when healthy. `EvalStatusBadge` renders `degraded`.
- Build + existing suites stay green.

## Risks / open questions

- **`_collected_errors` attribute name** is internal to the interpreter; confirm `EnsembleInterpreter` sets it on the same object the route holds (it does today via the header read). Use `getattr(..., 0)` defensively.
- **"Unavailable" definition** = not (`authenticated && action == 'healthy'`). `rate_limited` is borderline — treat as a warnable-unavailable too (it will also collect errors). Preflight message uses the per-backend `action`/`help_text` to be specific.
- **Degraded threshold:** any `collected_errors > 0` ⇒ degraded. (Not "all rows" — a partial outage that drops some rows is still degraded and worth surfacing. n=0 is the worst case.)
- Preflight is **advisory** (user can proceed); it never blocks a run outright, matching the robust-by-design philosophy.

## Summary

Surface backend-unavailability at both ends: an advisory preflight that warns before a run produces nothing, and a persisted `degraded` run status + reason (driven by the already-computed collected-error count) shown in Eval Studio. No change to the robust `on_error=collect` semantics.
