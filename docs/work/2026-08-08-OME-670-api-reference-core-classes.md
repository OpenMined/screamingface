---
ticket: OME-670
stack: repo
status: done
started: 2026-08-08
finished: 2026-08-09
---

# OME-670 — API reference for core classes

## Intent

Fifth sub-issue of `OME-666`. The six user guides list their "Main APIs" as unlinked code because
no reference exists to link to. This adds it for the classes a reader constructs or reads.

The Linear issue has no description, so the spec is `OME-666`'s API-reference paragraph. That
paragraph names six core classes; two of them do not exist (`sf.Case` is `CaseInfo`,
`sf.StudyReport` was merged into `Report`) and it omits most of the surface. `__all__` exports 36
names; the class-shaped ones are eighteen.

## Planned changes

- `public-docs/src/pages/sf-client/api/RecipesPage.vue` — Recipe, Model, Fusion,
  CorrectiveEnsemble
- `public-docs/src/pages/sf-client/api/BenchmarksPage.vue` — Benchmark, BenchmarkInfo, CaseInfo,
  ModelInfo
- `public-docs/src/pages/sf-client/api/ReportsPage.vue` — Report, CandidateResult, MemberResult,
  OperationInfo, Usage, Failure
- `public-docs/src/pages/sf-client/api/ClientsPage.vue` — Client, AsyncClient, Connection,
  ConnectionPanel
- `public-docs/src/navigation/sf-client.ts` — an `API Reference` group with a `Core classes`
  subgroup
- `public-docs/src/router/index.ts` — four routes under `/sf-client/api/`
- `public-docs/CLAUDE.md` — routes and navigation tables
- this ledger and `docs/tasks/2026-08-08-api-reference-core-classes.md`

## Test plan

`public-docs` has no test suite. Verification is the gates CI runs, plus:

- Every signature copied from source at `e387aefd`, not reconstructed from memory
- Every runnable line executed against a local engine before being written down
- Constraints stated only where the source raises explicitly
- `npx oxlint .` · `npx eslint .` · `npm run build` · `prettier --check` on touched files
- Light and dark theme, and 400px with no horizontal page scroll

## Acceptance

- Eighteen classes documented across four pages, grouped by what a reader is doing
- Eight full entries: signature, what it is, parameters, returns, raises where applicable, one
  runnable line
- Ten field tables: name, type, meaning, no invented examples
- No name appears that is absent from `__all__` at `e387aefd`
- Modules, top-level functions, errors, warnings and event types are absent; they are `OME-671`
- Gates green: lint, build, format on touched files

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus a prose pass over
  `public-docs/src/pages/sf-client/Index.vue` and the six pages under
  `public-docs/src/pages/sf-client/guides/`.
- **Commits:**
  - `757baff0` — the four API reference pages, nav group, routes, `public-docs/CLAUDE.md`
  - `0c0d45c9` — prose pass over the guides and Overview
- **Gates:** `npx oxlint .`, `npx eslint .`, `npm run build` and
  `prettier --check` all green. Sidebar nesting and long-repr wrapping confirmed
  visually by the owner at three levels of navigation depth.
- **Deviations:**
  - The `OME-666` spec named six core classes, two of which do not exist
    (`sf.Case` is `CaseInfo`; `sf.StudyReport` was merged into `Report`). The
    page set follows `__all__` at `e387aefd` instead: eighteen class-shaped
    names across four pages.
  - `sf.MAX_ATTEMPTS` is exported from `corrective.py` but not re-exported at
    package level, so the retry cap is stated as prose rather than referenced.
  - Union types in tables use non-breaking spaces so a type cannot break across
    lines.
  - The prose pass over the guides and Overview was added to this ticket at the
    owner's direction rather than filed separately. `QuickstartPage.vue` was
    excluded: its samples still target the pre-`OME-605` API and are due a
    rewrite that will cover its copy too.
  - Work happened in the shared checkout rather than a per-unit worktree.
