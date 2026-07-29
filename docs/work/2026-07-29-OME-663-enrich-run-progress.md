---
ticket: OME-663
stack: screamingface-studio-frontend
status: in_progress
started: 2026-07-29
finished:
---

# OME-663 — Enrich run-progress detail

## Intent

During a run, show which **member** models are answering, whether the **judge** is running, which
have **finished**, and **how many questions** are done (X / N) — beyond today's per-model status +
% bar.

## Planned changes

- `(studio)/ensembles/new/page.tsx`: pass `judge` into `RunsPanel`; extend `startRun` to simulate
  a judge/arbitration phase after members; running UI gains a `Members` group, a `Judge` row (when
  a judge is set), and a `X / N questions` counter derived from progress.

## Test plan

- Verify in-app: start a run → members animate answering→answered, judge shows waiting→arbitrating→done,
  question counter climbs to N. `npx tsc --noEmit` + `npm run lint` clean.

## Acceptance

- Run progress distinguishes members vs judge, shows finished state, and a question counter; gates pass.

## Outcome

- **Actual files:** `src/app/(studio)/ensembles/new/page.tsx` — `RunsPanel` gains a `judge` prop
  (passed from `EnsembleComposer`), a `judgeStatus` state, a `Members` group + a `Judge` row
  (waiting → arbitrating… → done), and a `X / N questions` counter derived from progress.
- **Commits:** on branch `OME-661-restructure-fusion-composer` —
  `feat(desktop): enrich run-progress with members/judge status and question counter`, `Refs: OME-663`.
- **Gates:** `npx tsc --noEmit` clean · `npm run lint` clean · `/ensembles/new/` HTTP 200.
- **Verification note:** the live run animation requires clicking Run (interactive) — verified at the
  code/gate level here; owner can eyeball the animation in-app.
- **Deviations:** running-state JSX wrapped in an IIFE to compute question-count locals; the judge is
  an arbitration indicator only (not added to `modelResults`).
