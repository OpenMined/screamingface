---
ticket: OME-668
stack: repo
status: done
started: 2026-08-06
finished: 2026-08-06
---

# OME-668 — User guides v1: connections, models, fusions, benchmarks, evaluation, URL4

## Intent

Second sub-issue of `OME-666`. `public-docs/` has an Overview and a Quickstart but no user guides,
so a reader who finishes the Quickstart has nowhere to go to understand connections, composition,
benchmarks, or reports. This unit adds six of the parent's ten guide pages; `OME-669` covers the
rest.

Written against `OME-605-screamingface-client-v1` @ `e387aefd`. That matters: the client moved
branches, and the parent's spec plus the merged Overview and Quickstart describe the older
`OME-400` API. Every code sample here is verified against `e387aefd` and executed against a local
Engine.

## Planned changes

- `public-docs/src/pages/sf-client/guides/ConnectionsPage.vue`
- `public-docs/src/pages/sf-client/guides/ModelsPage.vue`
- `public-docs/src/pages/sf-client/guides/FusionsPage.vue`
- `public-docs/src/pages/sf-client/guides/BenchmarksPage.vue`
- `public-docs/src/pages/sf-client/guides/EvaluationPage.vue`
- `public-docs/src/pages/sf-client/guides/Url4Page.vue`
- `public-docs/src/composables/useDocNavigation.ts` — replace `NavSection`/`NavItem` with one
  recursive `NavEntry` union: a group (title + children) or a link (title + path + optional
  children). `flatNav` walks recursively and collects links only
- `public-docs/src/components/layout/NavTree.vue` — new; renders one level and recurses, so a group
  renders as a label and a link as a `RouterLink`
- `public-docs/src/components/layout/DocLayout.vue` — replace the hand-rolled sidebar loop with
  `<NavTree>`
- `public-docs/src/navigation/sf-client.ts` — `User Guides` group with a nested `Compose` group;
  Overview becomes a plain top-level link, retiring the empty-title-section convention
- `public-docs/src/navigation/sdk.ts` — migrate to `NavEntry`
- `public-docs/src/router/index.ts` — six routes under `/sf-client/guides/`
- `public-docs/CLAUDE.md` — routes, navigation tables, and the navigation model
- this ledger and `docs/tasks/2026-08-06-user-guides-v1.md`

## Test plan

`public-docs` has no test suite and is not a registered stack in `.claude/sdlc.local.md`, so there
is no RED→GREEN loop. Verification is the gates CI runs, plus live execution and manual checks:

- `npx oxlint .` · `npx eslint .` — bare, as CI runs them
- `npm run build` (type-check + vite build)
- `npx prettier --check` on the touched files
- Every snippet executed against a local Engine on `:9108` with AI Gateway on `:9105`; real output
  goes on the page. `ifeval` only — deterministic grading, no judge spend
- Every API name checked against `e387aefd`
- Sidebar shows `User Guides` with the `Compose` child group; active state correct
- Prev/next traverses Overview → Quickstart → Installation → the six guides
- Six pages in light and dark theme, and at mobile width with no horizontal page scroll

## Acceptance

- Six guide pages exist and are reachable from the sidebar
- Sidebar renders `User Guides` with `Compose` as a non-clickable label and Models/Fusions indented
  beneath it
- Navigation entries are either a link (has a path) or a group (label + children); groups are never
  clickable and never appear in prev/next
- Prev/next traverses only pages: Overview → Quickstart → Installation → Connections → Models →
  Fusions → Benchmarks → Running an evaluation → Reproduce & share
- Each follows the parent's five-part shape: What it is · What you can do · Main APIs · How to ·
  Links
- Each ends with `Based on state at commit e387aefd`
- Every code sample uses only API present in `e387aefd`; no `StudyReport`, no reducers, no
  `benchmark.evaluate(...)`, no `draco-lite`
- Displayed output is real, from an executed run
- Pages compose from the existing `components/nb/` and `components/ui/` primitives; headings `h2`
  under `DocLayout`'s `h1`
- Gates green: lint, build, format on touched files

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** 21 changed, +1751 / −163. More than planned: the navigation refactor and the
  mobile navigation were added during the unit.
  - six guide pages under `public-docs/src/pages/sf-client/guides/`
  - `useDocNavigation.ts` (NavEntry union), `NavTree.vue` (new), `DocLayout.vue`,
    `TheNavbar.vue`, both `navigation/` files, `router/index.ts`
  - `components/nb/NbTextOut.vue` (new) and `nb/index.ts`
  - `Index.vue`, `InstallationPage.vue`, `QuickstartPage.vue` — version prop; the Overview also
    lost its "Where next" section
  - `public-docs/CLAUDE.md`, plus this ledger and the `docs/tasks` mirror
- **Commits:**
  - `0a4dab36` — feat(public-docs): model navigation as groups and links, add the User Guides tree
  - `a7ed90ba` — feat(public-docs): six SF Client user guides against the live SDK
  - `0c0161b3` — feat(public-docs): make the sidebar and product nav reachable on mobile
- **Gates:** `oxlint` and `eslint` clean (run bare, as CI does) · `build` succeeds ·
  `prettier --check` clean on every file this unit touched. `public-docs` has no test suite, so
  there is no RED→GREEN loop.
- **Deviations:** the navigation model was refactored (groups vs links) rather than patched;
  mobile navigation was added — a drawer plus a navbar product switcher — which was not in the AC
  and touches `TheNavbar`; the commit stamp renders once in the sidebar footer rather than at the
  foot of each guide; the Overview's "Where next" section was removed as duplicating the sidebar.
