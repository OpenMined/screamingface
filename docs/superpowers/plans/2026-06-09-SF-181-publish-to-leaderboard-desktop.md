# SF-181 / D-SCORE-006 — "Publish to Leaderboard" (SF desktop side)

**Owner:** Sergey (SF/Electron side). **Scoreboard side:** Dmitry — already merged (#259); see `docs/superpowers/plans/SF-181-scoreboard-sf-ingestion.md`.
**Confidence:** ≥95%.
**Asana:** https://app.asana.com/1/1185126988600652/task/1214568426736586

## Context

The user-initiated path that publishes a local `eval_run` aggregate to the public scoreboard. This is the **SF-desktop half** of the A+B paired ticket. The scoreboard half is **done and merged**: `POST /v1/scores` accepts the **nested-`client`** wire shape, `Idempotency-Key` dedup, `GET /v1/scores/{id}` read-back, and CORS `*` all exist, and the contract is pinned by `apps/scoreboard/tests/unit/test_sf_payload.py`. This plan builds the desktop dialog/hook/redaction to send **exactly** what that test asserts — nothing on the scoreboard changes.

Why now: Eval Studio (SF-242) lets users run local evals; there is no way to share a result to the public leaderboard. This adds that, with a privacy gate so users don't accidentally publish a url4 that references local-only data.

### Decisions (confirmed with user)
- **Redaction model:** grounded `/data/<hash>` blob-ref warning (the ticket's "private spec in `~/.screamingface/specs`" premise doesn't match reality — `/data/<id>` is a content-hash blob, no public/private spec concept exists). Warn + Sanitize / Cancel / Publish-anyway.
- **benchmark_id/spec_id:** parse `spec_name` on `:` if present; otherwise show editable required fields (`spec_id` prefilled = `spec_name`).
- **Scope:** SF-desktop only. Do **not** recreate `test_sf_payload.py` (already merged); build the payload to satisfy it.

## The pinned contract (from `test_sf_payload.py` + `scores/schemas.py`)

`POST <scoreboard>/v1/scores`, header `Idempotency-Key: <eval_run.id>`, body (`extra="forbid"` — send these keys only):
```jsonc
{ "version": 1, "benchmark_id": "hle", "spec_id": "hle-ensemble-three",
  "url4_expression": "...", "accuracy": 0.81, "total_questions": 1000,
  "correct_questions": 810, "ran_with_providers": ["claude","codex","gemini"],
  "submitted_by": null, "ran_at_local": "2026-05-04T11:55:00Z",
  "client": { "name": "screamingface-desktop", "version": "0.4.2", "platform": "darwin" },
  "metadata": null }
```
Hard constraints the desktop MUST respect:
- **Nested `client`** (flat `client_*` → 422). No extra keys.
- **`accuracy` must equal `correct/total` within 0.01** else 400 → **send `accuracy = correct_questions/total_questions`** (recomputed), not the stored rounded value.
- **`benchmark_id` must be pre-registered** else 404 → surface as actionable error; coordinate seeded benchmarks with Dmitry.
- Repeat POST with same key → **200 + same `id`** (one row).
- Response is **flat** `ScoreSchema`; read `id`, `benchmark_id`, `spec_id` for the toast deep link.

## Architecture

Self-contained renderer feature. Pure redaction lib → publish hook (HTTP + idempotency + retries) → dialog → button. Native `fetch()` to a configurable scoreboard URL. No SF-server changes.

### Files to create
- **`apps/desktop/src/renderer/src/lib/url4-redaction.ts`** — pure, no React:
  - `findLocalDataRefs(expr: string): string[]` — matches `/data/<ref>` segments (`/\/data\/[A-Za-z0-9_./-]+/g`).
  - `hasLocalDataRefs(expr): boolean`.
  - `sanitizeDataRefs(expr): string` — replaces each `/data/<ref>` with `/data/<redacted>`.
  - `parseSpecName(spec_name): { benchmark_id: string | null; spec_id: string }` — split on first `:`; no colon → `{ benchmark_id: null, spec_id: spec_name }`.
  - `deriveProviders(expr): string[]` — scan for known tokens `claude|codex|gemini|ollama` (dedup, ordered); `[]` if none.
- **`apps/desktop/src/renderer/src/lib/__tests__/url4-redaction.test.ts`** — exhaustive pure-fn tests (incl. the test fixture's `url4://ensemble(claude,codex,gemini)/hle` → `["claude","codex","gemini"]`).
- **`apps/desktop/src/renderer/src/hooks/use-publish-score.ts`** — `usePublishScore()` → `{ publish(args), status, error, result }`. Builds the exact nested payload (recomputed accuracy, providers, `submitted_by` null when blank, `ran_at_local = finished_at ?? started_at`, `client` from app version + `platform`), POSTs with `Idempotency-Key: <eval_run.id>`, **10s timeout, 3 retries (1s/2s/4s backoff)** on network/5xx only (never retry 4xx). Maps 404→"benchmark not registered", 400→"accuracy/aggregate mismatch", 422→"contract error". Reads scoreboard URL from config.
- **`apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx`** — custom-overlay modal following `components/session/NewSessionDialog.tsx` (the app does **not** use shadcn Dialog). Content per ticket: read-only aggregate (accuracy, correct/total, providers), read-only url4 via the existing **`@/components/Url4Viewer`** with the redaction warning when `hasLocalDataRefs`, benchmark_id/spec_id (parsed or editable), optional submitter name ("leave blank for anonymous"), privacy notice, and Sanitize / Cancel / Publish — Publish disabled until a `/data`-ref run is either Sanitized or the "I understand this exposes local data refs" checkbox is toggled. Uses `usePublishScore` + `useToast`.
- **`apps/desktop/src/renderer/src/components/eval/__tests__/PublishToLeaderboardDialog.test.tsx`** — vitest + @testing-library (jsdom): parse vs editable IDs, redaction warning + gating, sanitize swaps the sent expression, success toast + link, error/retry. Mocks `usePublishScore`/config.
- **`apps/desktop/src/renderer/src/hooks/__tests__/use-publish-score.test.ts`** — mock `fetch`: idempotency header present, nested-client body, recomputed accuracy, retry/backoff with fake timers, 4xx-no-retry, error mapping.

### Files to modify
- **`apps/desktop/src/renderer/src/components/eval/EvalRunDetail.tsx`** — add a "Publish to Leaderboard" button in the header row (beside `EvalStatusBadge`, ~line 44), enabled only when `status === 'done'` and `accuracy != null && total_questions`. Wire open/close + render `PublishToLeaderboardDialog`.
- **Config / preload:** add `scoreboard_url` and `portal_url` (read via `window.electronAPI.config.read()`, overridable by `SF_SCOREBOARD_URL`; dev default `http://localhost:9106`, portal default per D-SCORE-007). Add an `app:getVersion` IPC (main already uses `app.getVersion()`), exposed on `window.electronAPI` and typed in `preload/types.ts`. `client.platform` = `process.platform` (via preload/IPC, not in the sandboxed renderer).

### Reuse (don't reinvent)
`@/components/Url4Viewer` (read-only expression), `@/hooks/use-toast` (`useToast`), `@/hooks/use-eval-runs` (`useEvalRunDetail` data), `@/hooks/use-server-status`, the `NewSessionDialog` modal pattern, `window.electronAPI.config.read()`.

## Data flow
Button (done run) → dialog opens with `useEvalRunDetail` data → `parseSpecName` + `deriveProviders` prefill → user confirms IDs / name, resolves any `/data` warning → `usePublishScore.publish()` builds nested payload (accuracy recomputed) + POSTs with idempotency key → success: toast "Published — view on leaderboard" linking `<portal>/spec.html?benchmark=<id>&spec=<id>`; failure: error toast + retry. Local `eval_run` never mutated.

## Error handling
10s timeout; 3 retries (1s/2s/4s) on network/5xx only; 4xx surfaced immediately with specific copy (404 benchmark, 400 aggregate mismatch, 422 contract). Retry button on the failure toast. Idempotency key = `eval_run.id` so retries/double-clicks never dupe.

## Verification
- **Unit (vitest):** `cd apps/desktop && npm test -- url4-redaction PublishToLeaderboardDialog use-publish-score` — all green.
- **Contract (no change, must stay green):** `cd apps/scoreboard && uv run pytest tests/unit/test_sf_payload.py -q`. Manually diff the hook's emitted body against `_sf_payload()` in that file — keys and nesting must match exactly.
- **Gates:** desktop lint/typecheck (`npm run lint`, `tsc`); the run renders without console errors.
- **Manual e2e:** run scoreboard on :9106 with a benchmark seeded (e.g. `hle`); run SF desktop with `SF_SCOREBOARD_URL=http://localhost:9106`; complete a local eval; Publish; confirm one row via `GET /v1/scores/{id}`, the success toast deep link opens the portal, and a second Publish click does not dupe (200, same id). Try a run whose url4 has a `/data/<hash>` ref → warning appears; Sanitize → sent expression shows `/data/<redacted>`.

## Coordination / flagged
- **Seeded benchmarks** (Dmitry): publishing to an unregistered `benchmark_id` → 404. Confirm which benchmark ids exist before the paired e2e.
- **`portal_url` default** is pending D-SCORE-007; use the dev default until finalized.
- `ran_with_providers` derivation is heuristic (token scan); the editable fallback prevents sending a misleading empty list.

## Build sequence
1. `url4-redaction.ts` + tests (pure, fastest to lock down).
2. `app:getVersion` IPC + `scoreboard_url`/`portal_url` config + preload types.
3. `use-publish-score.ts` + tests (payload exactly matches `test_sf_payload.py`).
4. `PublishToLeaderboardDialog.tsx` + tests.
5. Wire the button into `EvalRunDetail.tsx`.
6. Gates + manual e2e against a local scoreboard.
