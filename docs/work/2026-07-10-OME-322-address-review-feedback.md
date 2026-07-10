---
ticket: OME-322
stack: scoreboard
status: done
started: 2026-07-10
finished: 2026-07-10
---

# OME-322 — address Dmitry's PR #379 review feedback (round 1)

## Intent

Dmitry left 4 substantive review comments on PR #379. Address the 3 that are clean,
well-scoped code fixes; the 4th (benchmark-identity mismatch: production's `hle` is
OpenMined's internal "News Hallucinations", not the real Humanity's Last Exam) spans
the benchmark registry/import contract/docs per his own note and is a design/data
decision, not a code fix — asked him directly on the PR thread instead of guessing.

## Planned changes

- `apps/scoreboard/src/scoreboard/scores/schemas.py`:
  - `BaselineImportRow.accuracy` — add `strict=True, allow_inf_nan=False` (keep the
    existing custom range validator/message as-is, don't replace it with `Field(ge=,
    le=)`, to avoid changing the error text a prior test already asserts on).
  - `BaselineImportRow.metadata` — add a depth+size bound validator so a deeply
    nested/oversized payload is rejected at import time, before it can ever reach
    storage or response serialization.
- `apps/scoreboard/src/scoreboard/scores/baseline_store.py`:
  - `import_baseline` — accept an optional `using_db` for transactional use.
  - new `import_many` — wraps a batch in one `in_transaction()`, all-or-nothing.
- `apps/scoreboard/src/scoreboard/import_baselines.py`:
  - `import_baselines()` delegates to `BaselineStore.import_many` instead of looping
    row-by-row itself.
- Tests: extend `test_schemas.py` (strict accuracy, metadata bounds),
  `test_baseline_store.py` (batch atomicity), `test_import_baselines.py` (same, via
  the CLI-facing function).

## Test plan

- Reject `accuracy: true`/`false` (bool coercion), a numeric string, and `NaN`/`Infinity`.
- Accept a plain float/int in range (regression — must keep passing).
- Reject metadata nested past a bound; reject metadata serializing past a byte bound;
  accept metadata within bounds (regression).
- Batch import: row 1 valid + row 2 unknown benchmark → raises, AND row 1 is NOT
  persisted (list_baselines returns empty for that benchmark afterward).

## Acceptance

- All 3 fixes land with tests proving the specific failure mode each one closes.
- All prior tests remain green and unmodified.
- `run_gates.py scoreboard` all green (same `--skip-append-only` situation as before,
  OME-369 fixes this but isn't merged yet).

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `schemas.py`, `baseline_store.py`,
  `import_baselines.py`, `test_schemas.py`, `test_baseline_store.py`.
- **Commits:** be2d082 — fix(scoreboard): harden baseline import per review (metadata, accuracy, batch)
- **Gates:** `run_gates.py scoreboard --skip-append-only` → ALL GATES GREEN (ruff,
  format, pyright 0 errors, pytest 104 passed/1 skipped, coverage 87.81% ≥ 80%).
- **Deviations:**
  1. Benchmark-identity mismatch (Dmitry's 4th comment) deliberately not addressed
     this cycle — replied on the PR thread asking him to pick a direction first, per
     owner decision.
  2. Kept the existing custom range validator for `accuracy` instead of moving the
     0-1 bound into `Field(ge=, le=)` as Dmitry's suggestion literally showed, so the
     error message a prior test asserts on doesn't change (rule 5). Added
     `strict=True, allow_inf_nan=False` via `Field` for the actual coercion/inf-nan
     fix; the range check stays a separate validator, same message as before.
  3. Bounded the `metadata` field only on the import DTO (the only writer today), not
     also on the response schema — the import bound already prevents the reported
     crash since nothing unbounded can reach storage. Noted as a deliberately minimal
     scope, not a missed spot.
