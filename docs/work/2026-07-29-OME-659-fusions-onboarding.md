---
ticket: OME-659
stack: screamingface-studio-frontend
status: in_progress
started: 2026-07-29
finished:
---

# OME-659 — Fusions list: onboarding & empty states

## Intent

Make the fusions list clear for a first-time user: an explicit empty state that guides to
connect models / create a first fusion, and stop silently disabling the "New" button (the
composer now has an inline picker that guides connecting providers).

## Planned changes

- `(studio)/ensembles/page.tsx`: "New" button always enabled → composer; a clear empty-state card
  ("No ensembles yet" + what it is + primary create + a "connect a model first" nudge when no
  provider is connected). Keep the Import url4 flow. Terminology stays "ensemble" (rename = OME-658).

## Test plan

- In-app: with no ensembles + no connected providers → guided empty state; New always clickable.
  `npx tsc --noEmit` + `npm run lint` clean.

## Acceptance

- Empty state guides the user; New is not dead-disabled; gates pass; owner confirms in-app.

## Outcome

- **Actual files:** `src/app/(studio)/ensembles/page.tsx` — "New Ensemble" always enabled; a guided
  empty-state card ("No ensembles yet" + what it is + primary create + a "connect a model" nudge when
  no provider is connected); removed the dead library gate + unused `Layers` import.
- **Commits:** on branch `OME-661-restructure-fusion-composer` —
  `feat(desktop): guided empty state + always-enabled create on the fusions list`, `Refs: OME-659`.
- **Gates:** `npx tsc --noEmit` clean · `npm run lint` clean · `/ensembles/` empty state verified via
  screenshot.
- **Deviations:** nudge keyed on provider-connected signal (the actual prerequisite the composer picker
  guides toward), not library count.
