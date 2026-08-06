---
ticket: OME-712
stack: url4-cloud
status: done
started: 2026-08-05
finished: 2026-08-05
---

# OME-712 — add a safe DRACO structural smoke protocol

## Intent

Give notebooks a low-cost Engine-owned path that exercises DRACO's complete architectural seams
without presenting a reduced run as a canonical DRACO score. Canonical `draco` remains unchanged;
`draco/smoke` is independently identified and revisioned.

## Planned changes

- Update the accepted Engine Benchmark spec and plan with the canonical/smoke distinction.
- Add a new append-only URL4 Cloud contract-test module for smoke identity and multiplicity.
- Refactor the DRACO definition behind one internal constructor used by canonical and smoke.
- Register smoke's private routes from the existing DRACO runtime and assets.

## Test plan

- RED: discovery exposes `draco/smoke` as a one-Case, non-canonical resource.
- RED: its URL4 contains one Judge invocation and slices the criterion collection to one.
- Regression: canonical DRACO still declares 100 Cases and five Judge invocations with no
  criterion slice.
- Boundary: smoke aggregation reports its own Benchmark id/revision and expects one Judge pass.
- Run focused DRACO/manifest tests, then the complete URL4 Cloud gate.

## Acceptance

- One Engine-owned smoke Evaluation traverses Candidate Invocation, retrieval, verdict binding,
  aggregation, typed failures, and the Candidate-result contract.
- Smoke evaluates one pinned Case, one criterion, and one Judge pass.
- Its metadata explicitly rejects canonical/publishable interpretation.
- Canonical DRACO URL4 and scoring multiplicity remain unchanged.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** the Engine spec/plan and this ledger; DRACO definition/runtime/aggregate;
  shared Benchmark selection metadata and REST Case projection; registry; one new focused smoke
  contract module; two approved exact-set expectation expansions.
- **Commits:** this focused smoke-protocol commit.
- **Gates:** RED first (missing `DRACO_SMOKE`; then public/private Case selection returned two
  rows instead of one). Focused suites green (64 tests before the Case-selection follow-up; 16
  Case/runtime tests after it). Complete `run_gates.py url4-cloud --skip-append-only`: ALL GATES
  GREEN — Ruff, format, Pyright, layering, and full pytest+coverage.
- **Deviations:** append-only enforcement was skipped under explicit owner approval for two
  existing exact contract expectations: the complete catalog id set and assembled Engine route
  set. No assertion was weakened; both sets gained only the new smoke identity/routes. The planned
  internal selection seam became `Benchmark.case_ids` so public discovery and private execution
  cannot disagree and a later pinned lite subset can reuse the same invariant.
