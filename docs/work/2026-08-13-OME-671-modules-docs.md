---
ticket: OME-671
stack: repo
status: done
started: 2026-08-13
finished: 2026-08-13
---

# OME-671 — Modules docs

## Intent

Sixth and last sub-issue of `OME-666`. Adds the API reference pages for what `OME-670` left out:
the modules, the top-level functions, the errors and warnings, the event types, and the
leaderboard values.

## Planned changes

New pages under `public-docs/src/pages/sf-client/api/`:

- `ModulesPage.vue` — the five modules and five top-level functions
- `ErrorsPage.vue` — the error hierarchy and what a diagnostic error carries
- `EventsPage.vue` — the seven event types
- `LeaderboardsPage.vue` — the five leaderboard values

Supporting:

- `src/navigation/sf-client.ts` — a `Modules & types` subgroup under `API Reference`
- `src/router/index.ts` — four routes
- `public-docs/CLAUDE.md` — routes and navigation tables
- this ledger and `docs/tasks/2026-08-13-modules-docs.md`

## Test plan

`public-docs` has no test suite. Verification is the gates plus:

- Every signature from `inspect.signature`, every field from `dataclasses.fields`, every literal
  from `typing.get_args`, against the client on `main`. Never from reading source.
- No page names a symbol absent from `__all__`
- No revision hash asserted in prose or a table
- `npx oxlint .` · `npx eslint .` · `npm run build` · `prettier --check`

## Acceptance

- The four pages exist, are reachable, and appear in the sidebar
- No page references a symbol the client does not export
- Gates green

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** the four pages, `src/navigation/sf-client.ts`, `src/router/index.ts`,
  `public-docs/CLAUDE.md`, this ledger and the mirror.
- **Commits:**
  - `<pending>` — the four pages and their wiring
- **Gates:** `npx oxlint .`, `npx eslint .`, `npm run build` and `prettier --check` green.
- **Deviations:**
  - **Scope was cut back sharply.** This unit originally also corrected the four `api/` pages, six
    guides and the Quickstart against the merged client, because `OME-670` had verified its
    reference at `e387aefd` on a branch that never merged, and `d73f7d2a` documented a `reducer=`
    API that exists only on unmerged `OME-400` branches. That work was committed as `b288b036`,
    then dropped: Irina had corrected the same pages independently in `9274e2de`, `1b6ccd09` and
    `79cf4314`, verified against `b698fcff`, which is newer than the `17f7643b` this branch used.
    On every fact compared the two agreed, so nothing was lost by taking hers.
  - Only the four new pages survive, since `main` has none of them. The branch was reset onto
    `main` rather than rebased, because all fourteen shared files conflicted and none of this
    side's version was worth keeping.
  - `CoverageWarning` was removed from the client between `17f7643b` and `d7ab1f31`.
    `ErrorsPage.vue` documented it in three places; all three are corrected to
    `EvaluationWarning`.
  - `src/lib/source.ts` was written and then dropped. It gave the version footer and the
    companion-notebook links one shared constant. Irina maintains the footer as a literal in
    `sf-client.ts`, so introducing it here would have moved a value she edits into a file she does
    not know about. Worth proposing separately: the footer pins `b698fcff` while the notebook links
    point at `blob/main`, so a reader clicking through gets notebooks from a different state than
    the prose describes.
  - `api/ReportsPage.vue` is untouched. Its examples need a live evaluation, and the OpenRouter key
    available during this unit was rejected upstream by the provider (`api_key_invalid`).
  - `InstallationPage.vue` states `len(sf.__all__)` is 53. It is 55 at `d7ab1f31`. Left alone
    because the page is Irina's and outside this scope.
  - `main` gained `CorrectiveLoop` and `SelfCorrective` while this ran. Neither is documented
    anywhere yet; they belong on `api/RecipesPage.vue`.
