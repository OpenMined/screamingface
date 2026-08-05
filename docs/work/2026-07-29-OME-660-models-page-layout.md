---
ticket: OME-660
stack: screamingface-studio-frontend
status: in_progress
started: 2026-07-29
finished:
---

# OME-660 — Rework the Models page layout

## Intent

The current three-column left→right flow (providers → models → library) reads awkwardly. Collapse
it to a clearer **two-pane** layout: a providers rail on the left, and a main area whose top holds
the model **library** (selected models + Build), with the selected provider's model grid below.

## Planned changes

- `(studio)/models/page.tsx`: left providers rail (grouped, connect inline); main = a library
  summary bar (selected-model chips + Build) over the selected provider's model grid. Remove the
  standalone right library column. Preserve connect/discover, add/remove-to-library, and the
  "Build an Ensemble" → composer recipe action. Terminology stays "ensemble" (rename = OME-658).

## Test plan

- In-app: select a provider, connect (mock), add/remove models, library bar updates, Build works.
  `npx tsc --noEmit` + `npm run lint` clean. Owner eyeballs the new layout (design-open — iterate).

## Acceptance

- Two-pane layout replaces the 3-column flow; all model flows preserved; gates pass.

## Outcome

- **Actual files:** `src/app/(studio)/models/page.tsx` — two-pane: providers rail (grouped, selectable
  rows) + main area with a top **library bar** (removable model chips + Build) over the selected
  provider's model grid; connect UI moved into the main header; the standalone right library column
  removed.
- **Commits:** on branch `OME-661-restructure-fusion-composer` —
  `feat(desktop): rework Models page into a two-pane layout`, `Refs: OME-660`.
- **Gates:** `npx tsc --noEmit` clean · `npm run lint` clean · fresh `/models/` layout verified via
  screenshot (connected/model-grid state needs interaction — owner can eyeball).
- **Deviations:** connect UI surfaced in the main header (a `w-64` rail row can't hold an API-key
  input cleanly); rounded shadcn styling kept (brand re-skin out of scope).

## Follow-up refinement (owner, 2026-07-30)

Replaced the top library bar with a **starred-models** model: a per-model **star** toggle (reusing
`library` as the starred set), a **★ Starred** rail entry listing starred models with per-model
**checkboxes**, and a **Compose a Fusion** action that stays **disabled until ≥1 is selected** (then
composes from the checked subset). Selected models no longer pop above the available ones. Renamed
"Build a Fusion" → **"Compose a Fusion"**. Commit: `feat(desktop): starred-models library +
compose-from-selection on the Models page`, `Refs: OME-660`.
