---
ticket: OME-934
stack: screamingface-engine
status: planning
started: 2026-08-22
finished:
---

# OME-934 — expose generic run-scoped structured Log seam

## Intent

Specify the smallest generic Runner port needed for observational features to emit structured Logs
without importing their domain semantics into Runner code.

## Planned changes

- `docs/spec/2026-08-22-OME-934-run-log-seam.md`
- `docs/plan/2026-08-22-OME-934-run-log-seam.md`
- one generic Runner port and executor/composition wiring fixed by the approved plan
- focused isolation, ordering, failure, and layering tests

## Test plan

- RED tests for exact URL4 handoff, ordinary Log delivery, concurrent isolation, and fail-open
  setup/emission/teardown.
- Regression fixtures for unchanged result, URL4 identity, existing Events, and errors.
- Layering test prohibiting Benchmark imports.

## Acceptance

- No Benchmark schema or semantics outside `/benchmarks`.
- No generated URL4 or `packages/url4` change.
- No production code before explicit approval of this issue's spec and plan.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** pending
- **Commits:** pending
- **Gates:** pending
- **Deviations:** pending
