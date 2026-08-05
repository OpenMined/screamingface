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

## Follow-up refinement (owner, 2026-07-30)

Clarified the run-detail view: part 1 now has a **Scoreboard** kicker ("How this run ranks") over the
ranking table; part 2 an **Inspect results** kicker ("Per-question answers and reasoning") separated
by a hairline + spacing so it reads as its own component. Space: the inspect box is taller
(`h-[30rem] min-h-[60vh]`), the question list wider (`w-72`), and the section spans the full container
so the reasoning pane gets more room. Presentational only. Commit: `feat(desktop): clarify run-detail
scoreboard vs inspect-results + use space better`, `Refs: OME-663`.
