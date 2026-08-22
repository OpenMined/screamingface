---
ticket: OME-934
stack: screamingface-engine
status: in_progress
started: 2026-08-22
finished:
---

# OME-934 — expose generic run-scoped structured Log seam

## Intent

Specify the smallest generic Runner port needed for observational features to emit structured Logs
without importing their domain semantics into Runner code, and finish its production composition
through one dormant Benchmark adapter so the first consumer requires no second core change.

## Planned changes

- `docs/spec/2026-08-22-OME-934-run-log-seam.md`
- `docs/plan/2026-08-22-OME-934-run-log-seam.md`
- one generic Runner port, local structured-Log bridge input, and executor lifecycle integration
- one task-local Benchmark recorder and registry adapter wired only at the composition root
- focused isolation, ordering, failure, composition, regression, and layering tests

## Test plan

- RED tests for exact URL4 handoff, same-bridge Log delivery, scalar validation, nested/concurrent
  isolation, ownership refusal, expired emitters, and fail-open setup/emission/teardown.
- Production `build_executor` proof for the wired but semantically dormant Benchmark adapter.
- Regression fixtures for unchanged result, URL4 identity, existing Events, errors, cancellation,
  early consumer exit, bridge pressure, and world teardown.
- Layering test allowing the concrete adapter only at the composition root.

## Acceptance

- No Benchmark schema or semantics in generic Runner modules.
- No `screamingface.evaluation-progress.v1` records in OME-934.
- No generated URL4 or `packages/url4` change.
- Owner approved the revised specification, plan, and implementation on 2026-08-22 before
  production code began.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** pending
- **Commits:** pending
- **Gates:** pending
- **Deviations:** pending
