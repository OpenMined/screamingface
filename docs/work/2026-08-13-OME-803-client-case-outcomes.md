---
ticket: OME-803
stack: py-screamingface
status: done
started: 2026-08-13
finished: 2026-08-13
---

# OME-803 — Consume normalized benchmark case outcomes in the Python Client

## Intent

PR #572 (OME-802) makes every Case Result on the `screamingface.candidate-result.v1`
wire carry explicit `status` (scored | refused | failed) and `refusal` keys. The client
decoder enumerates an exact key set and raises `ExecutionError` on unknown keys, so every
`sf.evaluate` decode fails against a #572 engine. This unit teaches the client the new
contract: decode the two keys strictly (mirroring `apps/url4-cloud/src/url4_cloud/benchmarks/contract.py`),
expose `status` and `refusal` on `sf.CaseResult`, and preserve them through `to_dict()`
export — without recalculating Benchmark semantics.

## Planned changes

- `packages/screamingface/src/screamingface/case_result.py` — `CaseStatus` type; `status`
  and `refusal` fields on `CaseResult` (derived when omitted, validated when given);
  `to_dict()` includes both.
- `packages/screamingface/src/screamingface/_evaluation/results.py` — `_case_result`
  required key set gains `status` and `refusal`; new `_case_status` literal decoder.
- Tests: new `tests/test_case_outcome_decoding.py`; updated wire fixtures in
  `tests/test_draco_vertical_slice.py`, `tests/test_benchmark_compilation.py`,
  `tests/test_benchmark_variant_selection.py`, `tests/test_client_run.py`,
  `tests/test_case_result_contract_boundaries.py`, `tests/test_case_results.py`.

## Test plan

- RED: `_case_result` decodes scored / refused / failed payloads carrying the new keys;
  `status` and `refusal` are exposed on the decoded object and in `to_dict()`.
- RED: missing `status` or `refusal` → `ExecutionError`; unsupported status text →
  `ExecutionError`; genuinely unknown keys still rejected (strict posture kept).
- Constructor invariants: explicit status must match the grade/refusal/failure shape;
  a scored Case cannot carry refusal text.
- All existing suite green after fixture updates (production decode paths only).

## Acceptance

- `uv run pytest -q` green in `packages/screamingface`.
- Decoder required key set is byte-for-byte the CaseResult field set of
  `url4_cloud/benchmarks/contract.py` at #572 head (all nine keys unconditional).

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned (`case_result.py`, `_evaluation/results.py`, six test
  files touched, one new test file).
- **Commits:** feat(screamingface): decode Case status and refusal from
  candidate-result.v1 (sha in PR)
- **Gates:** 717 passed, 1 skipped; ruff check + format clean; pyright 0 errors
  on touched files
- **Deviations:** string `case_id` support (contract's `CaseId = StrictInt | StrictStr`)
  deferred — every engine producer emits ints today; noted as PR follow-up.
