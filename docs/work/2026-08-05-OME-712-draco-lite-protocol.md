---
ticket: OME-712
stack: url4-cloud
status: done
started: 2026-08-05
finished: 2026-08-05
---

# OME-712 — add a bounded DRACO lite protocol

## Intent

Provide a materially cheaper directional DRACO preview without presenting the result as canonical.
Lite pins two Cases, ten criteria per Case, and one Judge pass per criterion.

## Planned changes

- Record the immutable two-Case and ten-criteria selection rule in the accepted Engine spec and plan.
- Add a new append-only lite contract module before production code.
- Extend the shared DRACO definition/runtime with `draco/lite`, reusing the Case-selection seam
  introduced by smoke.
- Expand only the exact catalog and assembled-route expectations after owner approval.

## Test plan

- RED: `draco/lite` is a distinct two-Case, ten-criteria, one-pass Benchmark.
- RED: public Case discovery and private execution expose exactly ids `2, 15`.
- Regression: smoke remains 1/1/1 and canonical remains 100/all/5.
- Boundary: lite result identity carries its own id/revision and one Judge pass.
- Run focused DRACO tests and the complete URL4 Cloud gate.

## Acceptance

- Lite evaluates exactly 20 Judge calls per Candidate: two Cases × ten criteria × one pass.
- Lite never claims canonical/full comparability.
- Its two Cases and criterion cap are pinned in revision identity, with Cases returned consistently through both Case
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
  `2, 15` map to Finance and Shopping/Product Comparison, both with 38 criteria; Lite takes the
  first ten criteria from each pinned rubric.
- **Deviations:** append-only enforcement was skipped under explicit owner approval for the same
  two exact contract expectations expanded by smoke: the complete catalog id set and assembled
  Engine route set. No assertion was weakened; both sets gained only the lite identity/routes.
  Lite runs 20 Judge calls per Candidate, while Candidate generation runs twice; actual spend
  depends on Candidate composition, retrieval, and output length.
