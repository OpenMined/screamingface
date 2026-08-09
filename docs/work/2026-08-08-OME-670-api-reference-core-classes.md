---
ticket: OME-670
stack: repo
status: in_progress
started: 2026-08-08
finished:
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

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:**
