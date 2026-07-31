---
ticket: OME-667
stack: repo
status: in_progress
started: 2026-07-30
finished:
---

# OME-667 — Update layout on the website + overview + quickstart

## Intent

First sub-issue of `OME-666` (Documentation for ScreamingFace Client V1). Every content page in
`public-docs/` is currently a 14-line component passing `DocLayout` a title and the literal text
`Stub page — replace with real content.` This unit delivers the three things in its title: the
sidebar **layout**, the **Overview** page, and the **Quickstart** page.

Branching follows the epic model: this branch is cut from
`callis/ome-666-documentation-for-screamingface-client-v1` and its PR targets that branch, not
`main`.

## Planned changes

- `public-docs/src/navigation/sf-client.ts` — Overview ungrouped, then a `Get Started` group with
  Quickstart and Installation
- `public-docs/src/composables/useDocNavigation.ts` — only if the empty-title section needs a type
  change
- `public-docs/src/components/layout/DocLayout.vue` — render no group heading when a section title
  is empty
- `public-docs/src/router/index.ts` — Quickstart route becomes `/sf-client/quickstart`
- `public-docs/src/pages/sf-client/Index.vue` — Overview page
- `public-docs/src/pages/sf-client/QuickstartPage.vue` — Quickstart page
- `public-docs/src/components/ui/` — one shared pending-figure affordance
- `public-docs/CLAUDE.md` — route and navigation tables

## Test plan

`public-docs` has no automated test setup and is not registered as a stack in
`.claude/sdlc.local.md`, so there is no RED→GREEN loop to run. Verification is the gate set the
project defines, plus manual render checks:

- `npm run type-check` · `npm run lint` · `npm run format` · `npm run build`
- Sidebar shows Overview ungrouped, then `Get Started`; active state correct
- Prev/next traverses Overview → Quickstart → Installation
- Quickstart resolves at `/sf-client/quickstart`
- Both pages in light and dark theme
- Both pages at mobile width with no horizontal scrolling of the page body

## Acceptance

- Sidebar shows Overview ungrouped, then `Get Started` with Quickstart and Installation; active
  state and prev/next work
- Quickstart resolves at `/sf-client/quickstart`
- Overview carries all five `OME-666` elements — what it is, headline gain figure, 6-line example,
  2-line how-it-works, links — and its example uses only shipped API
- Quickstart follows the six steps in order (`sf.config` → `sf.connect` → Models + Fusion →
  `sf.benchmarks.load("draco-lite@1")` → `benchmark.evaluate([candidates])` → read the
  `StudyReport`) and states the receipts: 1 case · 10 criteria · 1 judge pass · 7 solo + 9 Fusion
  candidates
- Unverified figures use one shared pending affordance
- Samples use `benchmark.evaluate(candidates)` → `StudyReport`
- Pages compose from existing `components/ui/` primitives; headings `h2` under `DocLayout`'s `h1`
- Both pages correct in light and dark theme, and at mobile width with no horizontal scrolling
- Gates green: type-check, lint, format, build

## Decisions taken in-session

- **Result figures are placeholders.** Owner-approved. No notebook under
  `packages/screamingface/examples/` has committed outputs, so no verified DRACO-Lite score exists
  to quote; producing one needs a paid run (~83 calls).
- **Receipts are real.** Verified from source: `_CRITERIA_LIMIT = 10` and `passes=1` in
  `_benchmarks/draco_lite.py`; one pinned case; `05_draco_quickstart.ipynb` builds 16 candidates
  (7 solo + 9 Fusions).
- **`baseline`/`gain` are not `StudyReport` fields.** `OME-666` lists them there, but `report.py`
  puts them on `Report` (single-candidate), where `baseline` is the best member score and
  `gain == score - baseline`. Quickstart reads `.best`, per-candidate `score`, and `.url4`; the
  Overview headline figure is a `Report.gain`. Correction raised with the owner.
- **Epic-level `docs/spec` and `docs/plan` deferred.** Owner's call, 2026-07-30 — the epic design
  stays in the `OME-666` Linear description for now.

## Blockers / notes

- **Linear MCP unavailable this session** — the issue status and close comment cannot be written
  from here. Owner action: activate via `/mcp`, or update `OME-667` manually.
- Landing label `repo`, milestone Week 3, priority Medium — inherited from `OME-666`.
- Nav entries, routes, and pages for User Guides and API Reference belong to the sibling sub-issues
  that own them.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** four, all under `public-docs/` — `src/navigation/sf-client.ts`,
  `src/components/layout/DocLayout.vue`, `src/pages/sf-client/Index.vue`,
  `src/pages/sf-client/QuickstartPage.vue`, plus `public-docs/CLAUDE.md`. Fewer than planned: no
  route change, no new component, no `NotebookViewer` wiring.
- **Commits:**
  - `6ffe4895` — feat(public-docs): sidebar layout plus Overview and Quickstart pages
  - `ca55dc2d` — fix(public-docs): distinguish sidebar group labels from their items
- **Gates:** `type-check` clean · `build` succeeds (326 ms) · `format` applied to the four touched
  files · `lint` reports 3 pre-existing `vue/multi-word-component-names` errors
  (`Collapsible.vue`, `sdk/Index.vue`, `sf-client/Index.vue`) — verified identical on a clean tree
  via `git stash`, so they are not introduced here and renaming components is out of scope.
- **Deviations:**
  - **Route left unchanged.** Planned to rename `/sf-client/quickstartPage` →
    `/sf-client/quickstart`; owner chose to keep the existing path to keep the diff small. The
    matching AC line in `OME-667` was amended. Stale `NOTEBOOK_ROUTES` entries were therefore left
    alone too.
  - **No `PendingFigure` component.** Design is owned separately and being actively changed, so the
    pending headline figure is plain prose inside the existing `.prose-content` styles rather than a
    new styled component.
  - **Hand-authored, not `NotebookViewer`.** `NOTEBOOK_ROUTES` maps `/sf-client` and the Quickstart
    route to notebooks, but it is stale scaffolding from the ported `syft-space-hub-docs`: it names
    `00_overview`, which exists nowhere in the SDK. The parent's per-page spec (outcome-first
    ordering, ≈ one screen, five named Overview elements) is not a notebook shape, and no `.ipynb`
    ships with the docs site.
  - **Repo-wide Prettier run reverted.** `npm run format` reformatted 20 files because Prettier had
    never been run here. Sixteen unrelated files were reverted so the diff stays scoped to this unit
    and does not collide with in-flight design work.
  - **Light/dark and mobile checks not performed by me.** Design ownership moved mid-ticket; the two
    pages use only existing layout primitives and add no styling of their own.
  - **Overview's "User guides" link renders as plain text**, not a link — that section has no route
    until the sibling sub-issues create it, and a dead link is worse than a marked placeholder.
