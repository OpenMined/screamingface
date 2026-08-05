---
ticket: OME-712
stack: url4-cloud
status: done
started: 2026-08-05
finished: 2026-08-05
---

# OME-712 — add a bounded DRACO lite protocol

## Intent

Provide a materially cheaper directional DRACO preview without sampling rubric criteria or
presenting the result as canonical. Lite preserves every criterion and reduces Cases plus Judge
repetition only.

## Planned changes

- Record the immutable five-Case selection rule in the accepted Engine spec and plan.
- Add a new append-only lite contract module before production code.
- Extend the shared DRACO definition/runtime with `draco/lite`, reusing the Case-selection seam
  introduced by smoke.
- Expand only the exact catalog and assembled-route expectations after owner approval.

## Test plan

- RED: `draco/lite` is a distinct five-Case, one-pass, all-criteria Benchmark.
- RED: public Case discovery and private execution expose exactly ids `2, 15, 40, 83, 34`.
- Regression: smoke remains 1/1/1 and canonical remains 100/all/5.
- Boundary: lite result identity carries its own id/revision and one Judge pass.
- Run focused DRACO tests and the complete URL4 Cloud gate.

## Acceptance

- Lite Judge multiplicity is 1% of canonical for an equivalent Candidate and average rubric size.
- Lite never samples criteria and never claims canonical/full comparability.
- Its five Cases are pinned in revision identity and returned consistently through both Case
  discovery and execution.
- Canonical and smoke contracts remain unchanged.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** the accepted Engine spec/plan and this ledger; the shared DRACO definition,
  runtime, and registry; one new append-only lite contract module; two approved exact-set
  expectation expansions.
- **Commits:** this focused lite-protocol commit.
- **Gates:** RED first (`DRACO_LITE` did not exist). Five new lite contract tests green; 60
  focused DRACO/catalog/connector tests green. Complete
  `run_gates.py url4-cloud --skip-append-only`: ALL GATES GREEN — Ruff, format, Pyright,
  layering, and full pytest+coverage. The pinned local assets independently confirm ids
  `2, 15, 40, 83, 34` map to Finance (38 criteria), Shopping/Product Comparison (38), Academic
  (39), Technology (38), and General Knowledge (37).
- **Deviations:** append-only enforcement was skipped under explicit owner approval for the same
  two exact contract expectations expanded by smoke: the complete catalog id set and assembled
  Engine route set. No assertion was weakened; both sets gained only the lite identity/routes.
  Lite is approximately 1% of canonical **Judge work** (5/100 Cases × 1/5 passes), while
  Candidate generation remains 5% and actual spend depends on Candidate composition and output.
