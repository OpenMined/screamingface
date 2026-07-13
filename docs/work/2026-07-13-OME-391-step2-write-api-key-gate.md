---
ticket: OME-391
stack: scoreboard
status: done
started: 2026-07-13
finished: 2026-07-13
---

# OME-391 (step 2 of 2) — placeholder API-key gate on score submission

## Intent

C2: `POST /v1/scores` accepts unauthenticated writes, so fabricated submissions can
affect public leaderboard integrity. Full identity (OME-326) doesn't exist yet, so
Irina + Kevin agreed to stub the write-path gate with a single shared placeholder API
key rather than block on it. Once OME-326 ships, this key check is swapped for real
per-user identity — `submitted_by` stays self-reported free text for now either way.

This intentionally has no per-user distinction: everyone holding the key looks
identical to the server. It resolves C2's acceptance criterion ("write path gated by
an accepted integrity mechanism") without answering the harder identity/attribution
question, which stays with OME-326.

## Planned changes

- `apps/scoreboard/src/scoreboard/config.py` — add `submission_api_key: str | None =
  None` to `Settings` (env `SCOREBOARD_SUBMISSION_API_KEY`, same pattern as every
  other setting here). Unset → gate is a no-op, preserving current behavior for local
  dev and all existing tests.
- `apps/scoreboard/src/scoreboard/routes/scores.py` — new `_require_submission_api_key`
  FastAPI dependency: reads `settings.submission_api_key` off `request.app.state`;
  if unset, returns immediately; if set, requires `Authorization: Bearer <key>` to
  match exactly, else `401`. Wired via `Depends()` on `submit_score` only — `GET
  /v1/scores/{id}` and all other routes stay public reads.
- No model/schema/migration change — this is a request-time config check, not
  persisted state.

## Test plan

- Unset key (default `Settings()`, all current fixtures): write without any
  `Authorization` header still returns 201 — proves backward compatibility, and this
  is exactly what the entire existing test suite already exercises unmodified.
- Key configured + correct `Authorization: Bearer <key>` → 201 (happy path).
- Key configured + missing header → 401.
- Key configured + wrong key → 401.
- Key configured + `GET /v1/scores/{id}` without any header → 200 (reads stay public
  even when the write gate is active — the invariant this whole design protects).

## Acceptance

- `POST /v1/scores` rejects writes with a missing/wrong key once
  `SCOREBOARD_SUBMISSION_API_KEY` is configured; behavior is unchanged when it isn't.
- All prior tests remain green and unmodified (no existing test sets the new setting).
- `run_gates.py scoreboard --skip-append-only` all green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `apps/scoreboard/src/scoreboard/config.py` — added `submission_api_key: str |
    None = None` to `Settings`.
  - `apps/scoreboard/src/scoreboard/routes/scores.py` — `_require_submission_api_key`
    dependency wired via `Depends()` on `submit_score` only; documented the 401 in
    `SUBMIT_SCORE_RESPONSES`; updated the two stale docstrings that claimed the write
    path was unconditionally unauthenticated.
  - `apps/scoreboard/tests/unit/test_scores_routes.py` — new `app_with_api_key` /
    `gated_score_client` fixtures; 5 new tests (unset-key no-op, correct key, missing
    key, wrong key, reads stay public under a configured key) + one added assertion
    on the pre-existing OpenAPI-schema test for the new 401 response.
  - `apps/scoreboard/README.md`, `apps/scoreboard/DEPLOYMENT.md` — documented the new
    env var and its no-op-when-unset / not-per-user semantics for operators.
- **Commits:** this unit's commit (`Refs: OME-391`).
- **Gates:** `run_gates.py scoreboard --skip-append-only` — ALL GATES GREEN (ruff
  check, ruff format --check, pyright, pytest). 118 passed, 1 skipped, 88.30%
  coverage.
- **Deviations:** none — matched the plan; all prior tests remained green and
  unmodified (no existing fixture sets the new setting, so the gate default is a
  true no-op as designed).
