---
ticket: OME-803
stack: screamingface
status: in_progress
started: 2026-08-13
finished:
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

- Strictly consume all nine OME-802 Case fields and the exact nested Failure wire.
- Preserve explicit outcomes, exact text, and string/integer Case identity in public values,
  `.by_id()` lookup, Report serialization, file export, and the submitted URL4 receipt.
- Present scored, refused, failed, and partial-evidence unscored Cases distinctly, including exact
  refusal/failure detail and a reason whenever a Candidate score is withheld.
- Pin the shared contract with DRACO, IFEval, and HealthBench fixtures plus renderer and vertical
  slice coverage.

## Test plan

- Every outcome and Benchmark family decodes and round-trips through one contract.
- Every missing structural key, unknown key/status, malformed nested Failure, mismatched Case
  identity, and contradictory outcome shape fails before presentation.
- String and zero-valued Case identifiers, exact whitespace-bearing wire text, ID lookup, report
  JSON/file export, status-driven widgets, and exact submitted URL4 preservation are covered.
- Complete `screamingface` gates green.

## Acceptance

- `uv run pytest -q` green in `packages/screamingface`.
- Decoder required key set is byte-for-byte the CaseResult field set of
  `url4_cloud/benchmarks/contract.py` at #572 head (all nine keys unconditional).

## Outcome (ready for review; close after merge)

- **Production:** strict Case/Failure decoding; shared exact-preserving Case identity validation;
  public `CaseResult.status`/`refusal`; explicit `.cases.by_id()`; lossless Report export; and
  status-driven refused/failed/unscored presentation with complete Failure disclosures.
- **Tests:** three Benchmark-family contract fixtures, every Case key required, exact text/ID
  round-trips, outcome invariants, lookup/export, UI states, withheld-score explanations, and a
  normal evaluation receipt proving `result.url4` equals the submitted transport expression.
- **Current verification:** 742 passed, 1 skipped; Ruff check/format, Pyright, ≥95% coverage,
  notebook consistency, package build, and distribution inspection are all green.
- **Append-only exception:** the gate is run with `--skip-append-only`. Existing contract fixtures
  must add mandatory `status`/`refusal`; inherited boundary/serialization tests must adopt the
  required full Failure shape and string IDs; the obsolete Client-only snake-case Failure-code
  restriction is replaced by a positive test of the Engine's open non-empty contract; report tests
  assert explicit outcome semantics; and the vertical slice records the exact submitted URL4.
  These are contract migrations and new positive assertions, not removals that weaken coverage.
- **Process deviation:** Khoa's initial three implementation commits existed before the branch had
  OME-803 spec/plan files. The user had explicitly approved the design and implementation in the
  working conversation; the missing repository artifacts were added during review. This is
  disclosed rather than rewriting history to imply a chronology that did not occur.
