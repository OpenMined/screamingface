---
ticket: OME-773
stack: url4-cloud
status: done
started: 2026-08-11
finished: 2026-08-11
---

# OME-773 — Promote the candidate-result contract to a pydantic model in the engine

## Intent

The `screamingface.candidate-result.v1` shape is hand-built dicts in each benchmark
aggregate; its invariants live in comments and per-benchmark tests, and were violated
twice on PR #543 (missing check `outcome`, missing canonical `pass_rate`/`coverage`),
surfacing as wrong/empty report widgets debugged from screenshots. Encode the contract
once as a pydantic model constructed by every aggregate so a wrong shape fails at
construction in unit tests, not in the SDK UI.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/contract.py` — add `CandidateResult`
  (+ supporting models/validators); keep `CANDIDATE_RESULT_SCHEMA`.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/aggregate.py` — both reducers
  return `CandidateResult(...).model_dump()`.
- DRACO's result assembly (locate builder; `draco/` package) — same migration.
- `apps/url4-cloud/tests/unit/` — contract-model tests (validators fire on: scored
  without trio; unscored with metrics; graded check without outcome); existing
  ifeval/draco suites stay green unchanged (wire-compat proof).

## Test plan

- RED: model tests asserting ValidationError for each violated invariant, plus a
  wire-compat test that a known-good dict round-trips `model_dump()` byte-equal.
- GREEN: migrate aggregates; full `-k "ifeval or draco"` suites pass untouched.

## Acceptance

- Every scored aggregate on this branch constructs `CandidateResult`; invalid shapes
  raise named validator errors; existing 103 ifeval + draco tests pass unmodified.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `contract.py` (+`CandidateResult`),
  `ifeval/aggregate.py` (3 return sites), `draco/aggregate.py` (2 return sites),
  new `tests/unit/test_candidate_result_contract.py` (6 tests incl. wire-compat
  key-order proof); plus this ledger + `docs/tasks/` mirror.
- **Commits:** (sha filled on commit) feat(url4-cloud): construct candidate results
  through a pydantic contract model
- **Gates:** `pytest -k "ifeval or draco or candidate_result"` → 222 passed
  (216 pre-existing untouched + 6 new); ruff clean.
- **Deviations:** check-level MET/UNMET outcome NOT enforced in the model —
  discovered DRACO's checks carry verdicts only per judge pass (evidence level),
  so a single check-level outcome needs a multi-run roll-up design first;
  documented in the model docstring, pinned meanwhile by ifeval's tests.
  HealthBench migration deferred to PR #544
  (`.dk/plans/2026-08-11-healthbench-canonical-metrics.md`).
