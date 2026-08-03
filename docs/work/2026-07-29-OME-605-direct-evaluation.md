---
ticket: OME-605
stack: screamingface
status: done
started: 2026-07-29
finished: 2026-07-29
---

# OME-605 — Replace public planning with direct evaluation

## Intent

Implement the owner-approved single-operation Client interface so researchers evaluate Candidates
without learning or managing an intermediate Plan.

## Planned changes

- Add the approved direct-evaluation spec and implementation plan.
- Replace public `plan`/`run` operations with explicit Client `evaluate`.
- Make planning values internal implementation details.
- Update active package documentation and deterministic examples.
- Replace explicitly superseded unreleased public-contract tests while preserving compilation,
  URL4, lifecycle, and Report invariants.

## Test plan

- Drive the interface change with failing sync, async, validation, ordering, and removed-surface
  tests.
- Run focused tests, the full package suite, coverage, notebook checks, type checking, linting,
  formatting, and distribution checks.

## Acceptance

- `Client.evaluate(...)` and `AsyncClient.evaluate(...)` are the only public execution operations.
- Callers provide Candidates, Benchmark, optional limit, Event callback, and progress preference
  in one call.
- Compilation remains no-spend and completes before Candidate execution begins.
- Reports retain each Candidate's exact URL4 and declared order.
- Active documentation contains no public Plan workflow.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added the approved direct-evaluation spec/plan and focused tests; consolidated
  synchronous/asynchronous compilation, progress observation, transport, and Report assembly
  behind `Client.evaluate(...)`; privatized compiled Evaluation values; removed the public
  Plan/Candidate display path; updated package exports, README, deterministic notebook sources,
  generated notebooks, examples, package metadata, and affected tests.
- **Commits:** not committed; the user asked to continue without committing.
- **Gates:** 223 passed / 15 skipped; 95.75% coverage; Ruff, formatting, Pyright, deterministic
  notebooks, wheel/sdist build, distribution checks, and `git diff --check` passed.
- **Deviations:** the repository wrapper's append-only precheck reports the intentional replacement
  of tests and notebooks that specified the superseded unreleased Plan interface. This exact
  migration was owner-approved, user-approved, and recorded in the OME-605 migration exception;
  the wrapper has no exception mechanism. No technical gate failed.
