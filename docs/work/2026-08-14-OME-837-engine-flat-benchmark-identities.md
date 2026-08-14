---
ticket: OME-837
stack: url4-cloud
status: done
started: 2026-08-14
finished: 2026-08-14
---

# OME-837 — Engine flat benchmark identities

## Intent

Make Engine benchmark identity flat and remove development variants from public discovery.

## Planned changes

- Remove DRACO lite/smoke code and tests.
- Rename HealthBench routes and remove `variant` from the benchmark wire contract.

## Test plan

- Foundation wire tests, canonical DRACO tests, HealthBench tests, and full URL4 Cloud gates.

## Acceptance

- Engine discovery exposes only `draco`, `ifeval`, and `healthbench-worst30` without `variant`.

## Outcome

- **Actual files:** benchmark definition/catalogue/REST contract; canonical-only DRACO definition,
  runtime, assets, scoring, and aggregation; flat HealthBench routes; canonical protocol tests.
- **Commits:** this branch's squash-ready OME-836 implementation commit.
- **Gates:** URL4 Cloud lint, format, pyright, layering, and full coverage gate green.
- **Deviations:** variant-only tests were deleted by design. Canonical DRACO's dormant criterion
  selection hooks were also removed after the deletion audit found they served only lite/smoke.
  Canonical Judge-count and seed-uniqueness guards were retained in the shared protocol suite.
