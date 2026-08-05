---
ticket: OME-658
stack: screamingface-studio-frontend
status: in_progress
started: 2026-07-29
finished:
---

# OME-658 — Rename user-facing "ensemble" → "fusion" (copy only)

## Intent

Rename every user-facing occurrence of "ensemble" to "fusion" across the studio UI. Copy only —
route paths (`/ensembles`), TS types (`SavedEnsemble`), hooks/vars/props, component & file names,
and localStorage keys (`screamingface-ensembles`) stay unchanged (no data migration).

## Planned changes

- Display strings across `components/app-sidebar.tsx`, `(studio)/page.tsx`, `(studio)/ensembles/*`,
  `(studio)/models/page.tsx`, `(studio)/leaderboard/page.tsx`, etc.: Ensemble→Fusion,
  ensemble→fusion, Ensembles→Fusions ("My Ensembles"→"My Fusions", "New Ensemble"→"New Fusion",
  "Build an Ensemble"→"Build a Fusion", "All ensembles"→"All fusions", …).

## Test plan

- `npx tsc --noEmit` MUST stay clean (proves no type/route/identifier was renamed) + `npm run lint`
  clean; grep confirms route hrefs still `/ensembles` and the localStorage key is untouched. Screenshot
  the sidebar/dashboard to confirm "Fusions" copy.

## Acceptance

- All visible copy says "fusion"; routes/types/keys unchanged; gates pass; owner confirms in-app.

## Outcome

- **Actual files:** display-string rename across `components/app-sidebar.tsx`, `app/(studio)/page.tsx`,
  `(studio)/ensembles/page.tsx`, `(studio)/ensembles/new/page.tsx`, `(studio)/leaderboard/page.tsx`,
  `(studio)/models/page.tsx`, `(studio)/scripts/page.tsx`, `app/layout.tsx`, `app/updates/page.tsx`;
  plus the default fusion name `"ensemble-1"` → `"fusion-1"` (shown in the composer).
- **Commits:** on branch `OME-661-restructure-fusion-composer` —
  `feat(desktop): rename user-facing ensemble -> fusion (copy only)`, `Refs: OME-658`.
- **Gates:** `npx tsc --noEmit` clean (proves no type/identifier renamed) · `npm run lint` clean ·
  grep confirms `/ensembles` routes + `screamingface-ensembles` key unchanged · dashboard/sidebar
  copy verified via screenshot.
- **Deviations:** left as-is (correctly): all identifiers/types/hooks (`SavedEnsemble`,
  `useEnsembleStore`, `ensembleId`, …), route paths, the localStorage key, the `kind: "ensemble"`
  data union, the `url4://…` recipe address, and a Python docstring inside a script template.
