---
ticket: OME-836
stack: repo
status: done
started: 2026-08-14
finished: 2026-08-14
---

# OME-836 — Flat benchmark identities

## Intent

Coordinate one atomic public identity cleanup across URL4 Cloud and the ScreamingFace Client.

## Planned changes

- Add the accepted cross-stack spec and plan.
- Deliver OME-837 and OME-838 without compatibility behavior.

## Test plan

- Both child stack gate suites and a final retired-identity search.

## Acceptance

- The OME-836 spec is true in Engine discovery, Client discovery, and examples.

## Outcome

- **Actual files:** OME-836 spec/plan/task mirrors; URL4 Cloud benchmark definitions/runtime;
  ScreamingFace discovery, Leaderboard validation, examples, tests, and docs; exact local
  Scoreboard seeding; public Client documentation.
- **Commits:** this branch's squash-ready OME-836 implementation commit.
- **Gates:** URL4 Cloud, ScreamingFace, and Scoreboard stack gates green; public-docs Prettier,
  ESLint, Vue type-check, and production build green.
- **Deviations:** append-only checking was skipped intentionally because the accepted removal
  deletes variant tests and obsolete notebooks. The repo-wide audit expanded the Client child to
  remove stale curated demos and public docs that still advertised retired identities. A final
  review also restored canonical DRACO cache-slot guards, rejected partial Leaderboard
  publication, and made exact local seeding fail safely around stored results.
