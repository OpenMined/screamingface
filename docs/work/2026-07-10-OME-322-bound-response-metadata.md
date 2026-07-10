---
ticket: OME-322
stack: scoreboard
status: done
started: 2026-07-10
finished: 2026-07-10
---

# OME-322 — bound BaselineSchema.metadata + make list_baselines resilient to a bad row

## Intent

Dmitry's 3rd round follow-up (non-blocking, PR already approved): a deeply
nested/oversized `metadata` value that somehow reaches the DB still crashes
`GET /v1/leaderboard/{id}` with a 500 on SQLite (PostgreSQL rejects it at insertion
instead) — so today, one bad row can make the whole board unavailable, and the
failure mode is database-dependent. `BaselineImportRow` already bounds `metadata` at
import time (round 2), but `BaselineSchema` (the read side) has no such bound, and
`list_baselines()` has no defense if a row still fails to convert.

Chose option C (discussed with owner): bound `BaselineSchema.metadata` too (shared
validator, consistency), AND make `list_baselines()` skip a row that fails to convert
instead of raising — that's the part that actually keeps the board available when one
row is bad, not just moving where the same crash happens.

## Planned changes

- `apps/scoreboard/src/scoreboard/scores/schemas.py`: extract the existing
  depth/size check out of `BaselineImportRow.validate_metadata` into a shared
  `_validate_bounded_metadata` function; add the same `@field_validator("metadata")`
  to `BaselineSchema` calling it.
- `apps/scoreboard/src/scoreboard/scores/baseline_store.py`: `list_baselines()` —
  catch a conversion failure per row, skip that row (log via `print` to stderr; no
  logging convention exists yet in this app), keep returning the rest.

## Test plan

- `BaselineSchema` construction: valid metadata passes (regression); oversized/deep
  metadata raises.
- `list_baselines()`: seed one good row + one row whose metadata bypasses the import
  guard (inserted directly via the model, not through `BaselineImportRow`) with
  oversized metadata → the good row is still returned, the bad one is silently
  dropped, not a crash.

## Acceptance

- A single bad row never prevents `GET /v1/leaderboard/{id}` from returning the good
  rows.
- All prior tests remain green and unmodified.
- `run_gates.py scoreboard --skip-append-only` all green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `schemas.py` (shared `_validate_bounded_metadata` +
  `BaselineSchema` validator), `baseline_store.py` (`list_baselines` skip-on-error),
  `test_schemas.py`, `test_baseline_store.py`.
- **Commits:** ade85fa — fix(scoreboard): bound response metadata + skip a bad baseline row
- **Gates:** `run_gates.py scoreboard --skip-append-only` → ALL GATES GREEN (ruff,
  format, pyright 0 errors, pytest 113 passed/1 skipped, coverage 88.16% ≥ 80%).
- **Deviations:** none — matches the plan (option C, agreed with owner). Confirmed via
  test that the validator alone (without the store-side fix) still raised at
  construction time — proving the skip-on-error logic in `list_baselines` is the part
  that actually keeps the board available, not just the added validator.
