---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 7D distinguish skipped benchmark cases

## Intent

Make early-stop reports reflect what actually happened. Cases deliberately left unscheduled after
a canary failure must be shown as skipped, separately from the case that genuinely reached and
failed at the engine, so researchers never mistake bookkeeping records for model requests.

## Planned changes

- Give SDK-generated unscheduled case records one stable `not_scheduled` code while retaining the
  original canary cause in their safe message.
- Update the report display to count and render failed versus skipped cases separately.
- Preserve a whitelisted, provider-agnostic reason category from known AI Gateway failure messages
  while continuing to discard raw upstream text.
- Add append-only execution and display tests for an early-stop report with one failure and four
  skipped cases.
- Diagnose the observed Gemini `provider_unavailable` from current local logs without making a new
  paid model call or changing AI Gateway.

## Test plan

- RED: an early-stop run stores `not_scheduled` for every case that never reached the engine.
- RED: a zero-score report says one case failed and four were skipped, with distinct sections and
  no claim that every selected case failed.
- RED: known Gateway failure shapes surface a safe reason category; unrecognized/private text is
  still omitted.
- Preserve ordinary complete, partial, and all-genuinely-failed report rendering.

## Acceptance

- The five-case canary scenario is visually reported as `1 failed · 4 skipped`, not five failures.
- Failure details show the real provider failure once; skipped details explain the stopping cause.
- Public score/baseline/gain semantics and actual scheduling behavior do not change.
- All ScreamingFace format, lint, typecheck, test, and 95% coverage gates pass.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** `src/screamingface/run.py`, `src/screamingface/_execution.py`,
  `src/screamingface/_report_display.py`, `apps/screamingface-engine/src/screamingface_engine/gateway.py`,
  and focused execution, report-display, connection-preflight, and Gateway tests.
- **Commits:** `feat(screamingface): polish live benchmark workflows` (this commit).
- **Gates:** authoritative SDK gate green; 527 SDK tests at 95.26% coverage; 135 engine tests at
  95.55% coverage; all seven notebooks regenerate byte-identically; fixtures and wheel/sdist build
  pass.
- **Deviations:** the completed failing run's exact Gemini diagnostic could not be recovered because
  neither existing service log retained its safe detail. Read-only inspection confirmed exactly two
  Gateway chat requests and an active Gemini OAuth connection with no stored authentication error.
  Future known provider failure shapes now retain only a whitelisted reason category; no AI Gateway
  or url4 package change and no additional model request were made.
