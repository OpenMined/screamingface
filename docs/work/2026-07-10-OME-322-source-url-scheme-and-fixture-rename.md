---
ticket: OME-322
stack: scoreboard
status: done
started: 2026-07-10
finished: 2026-07-10
---

# OME-322 — restrict source_url scheme + rename demo test fixtures away from hle

## Intent

Second round of Dmitry's PR #379 review. Two items:
1. `BaselineImportRow.source_url` accepts any string, including `javascript:`/`data:`
   URIs, which the public API returns and a future client could render as a link.
2. Non-blocking cleanup he suggested: rename the `hle` benchmark id used in this
   ticket's test fixtures to a neutral placeholder, since production's real `hle` is
   an unrelated demo dataset (tracked separately as OME-396) — avoids reinforcing an
   ambiguity these tests never meant to claim.

Filed OME-396 for the actual registry/canonical-id decision; that's out of scope here.

## Planned changes

- `apps/scoreboard/src/scoreboard/scores/schemas.py`: `BaselineImportRow.source_url` —
  add a field_validator requiring an `http://`/`https://` prefix (consistent style
  with the other custom validators in this file, not a raw `Field(pattern=...)`), plus
  `Field(max_length=2048)` to match the DB column limit.
- Rename `benchmark_id="hle"` to a neutral placeholder (`demo-benchmark`) across this
  ticket's OWN test fixtures in `test_baseline_store.py`, `test_import_baselines.py`,
  and the leaderboard-route baseline tests. This touches prior-cycle test bodies —
  explicitly authorized by the owner (not a silent rule-5 violation) — full test suite
  run required after to confirm nothing regresses.

## Test plan

- Reject `javascript:alert(1)`, `data:text/html,...`, and a plain non-URL string for
  `source_url`.
- Accept a valid `https://` URL (regression).
- Reject a `source_url` over 2048 chars.
- After the fixture rename: full suite green, same pass count as before (rename only,
  no behavior change).

## Acceptance

- New validator tests pass; all prior tests pass under their new fixture names.
- `run_gates.py scoreboard --skip-append-only` all green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `schemas.py`, plus renamed fixtures in
  `test_schemas.py`, `test_baseline_store.py`, `test_import_baselines.py`, and (only
  the 2 baseline-specific tests, via explicit override, not the shared helper default)
  `test_leaderboard_routes.py`. Also filed OME-396 (Linear, not a repo file).
- **Commits:** 420d081 — fix(scoreboard): restrict baseline source_url to http(s), rename demo fixtures
- **Gates:** `run_gates.py scoreboard --skip-append-only` → ALL GATES GREEN (ruff,
  format, pyright 0 errors, pytest 109 passed/1 skipped, coverage 87.91% ≥ 80%).
- **Deviations:** none — matches the plan. Fixture rename in
  `test_leaderboard_routes.py` was scoped to only the 2 baseline-specific tests
  (explicit `benchmark_id`/`display_name` override), not the shared `_register_benchmark`
  default or any of the pre-existing, unrelated score/leaderboard tests that also use
  "hle" — renaming those would have been out of scope and touched tests this ticket
  doesn't own.
