---
ticket: OME-843
stack: url4-cloud
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-843 — Capture member and synthesis output text in benchmark case artifacts

## Intent

First slice of OME-784. A Fusion case artifact keeps only the fused answer; each member
model's answer (and the synthesis step's, when it differs from the case output) is
discarded at the engine, so contribution analysis ("did the solos lack the substance or
did the synthesizer drop it?") requires paid re-runs. Persist per-operation output text +
finish_reason into the case artifact, keyed by the stable operation_id from the Candidate
operation projection. Client-side consumption stays in OME-699; the rest of the evidence
scope stays in OME-784.

## Planned changes

Spec: `docs/spec/2026-08-17-OME-843-member-output-capture.md` (envelope-widening via the
OME-796 `execution` precedent; telemetry route ruled out — nested candidate run is
unobserved). Engine side, pending plan approval:

- `apps/url4-cloud/src/url4_cloud/benchmarks/operation_outputs.py` (new recorder)
- `apps/url4-cloud/src/url4_cloud/benchmarks/invocation.py` (start capture)
- `apps/url4-cloud/src/url4_cloud/runner/connector.py` (contribute output+finish_reason)
- `apps/url4-cloud/src/url4_cloud/benchmarks/candidate_adapter.py` (binding derivation)
- `apps/url4-cloud/src/url4_cloud/benchmarks/contract.py` (`CandidateInvocation.operations`,
  `CaseResult.operations`)
- `apps/url4-cloud/src/url4_cloud/benchmarks/{evaluation,case_records,aggregation}.py` (thread)

Client tolerance (`results.py` optional key) is a separate lockstep sub-issue shipping first.

## Test plan

- RED first: contract round-trip for `operations` in `test_candidate_result_contract.py`;
  fusion-run capture attributing by binding (incl. duplicate-route → null invariant:
  "never guessed, never fabricated"); solo-run artifact byte-identical (invariant: no
  member section invented); conformance sweep across draco/ifeval/healthbench aggregates;
  protocol-expression test stays untouched/green.

## Acceptance

- Given a Fusion run, the case artifact carries each member operation's output text and
  finish_reason keyed by operation_id; single-model candidates' artifact shape unchanged;
  unavailable values stay null; report remains JSON-serializable and deterministic.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** new `url4_cloud/operation_calls.py` (task-local recorder + identity
  contextvar), new `benchmarks/operation_outputs.py` (expression parse + fingerprint
  attribution); `benchmarks/contract.py` (`OperationOutput`, optional `operations` on
  `CandidateInvocation` + `CaseResult` via exclude_if, encode/decode); `runner/connector.py`
  (identity scope + terminal record); `benchmarks/invocation.py` (capture + attach on both
  exits); `benchmarks/evaluation.py` (`CandidateAnswer.operations`); `benchmarks/
  case_records.py` (key only when attributed); `benchmarks/aggregation.py` (4 builders +
  grading_failure + `_operation_outputs`); adapters draco/case_results.py,
  ifeval/{runtime,aggregate}.py, healthbench/{aggregate,case_evaluation}.py;
  tests/unit/test_operation_output_capture.py (12 tests incl. connector e2e).
- **Commits:** (filled post-commit)
- **Gates:** run_gates.py url4-cloud ALL GREEN — ruff check/format, pyright, layering,
  pytest 1476 passed/5 skipped (cov ≥80), append-only test check.
- **Deviations:** healthbench `_valid_case_record` and the invocation decode shape check
  tolerate the `operations` key as the ONE optional deviation (absence stays absence),
  so pre-capture records and every existing fixture stay valid. Client tolerance shipped
  first as PR #613 (separate ledger `2026-08-17-OME-843-client-operations-key.md`).
  Dedicated client sub-issue still pending Linear re-auth.
