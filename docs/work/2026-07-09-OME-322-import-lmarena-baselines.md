---
ticket: OME-322
stack: scoreboard
status: done
started: 2026-07-09
finished: 2026-07-09
---

# OME-322 — Import single-model baselines (mechanism only, backend/API)

## Intent

The public scoreboard only shows community-submitted `Score` rows (URL4 ensemble
runs) — there's no "line to beat" showing what a single frontier model already
scores, so users can't tell whether an ensemble is actually beating a strong
baseline. Add a mechanism to import single-model baseline scores (from LMArena /
Artificial Analysis) with source attribution, surfaced through the existing
leaderboard read path.

Scoping decisions agreed with the owner (2026-07-09): build the import mechanism
only — no real baseline numbers seeded this pass (`livetruth`/`livetruth-latest` are
OpenMined-proprietary; only `hle` has real external single-model data, left for a
follow-up once sourced) — and backend/API only, no portal "target line" rendering
(explicit follow-up).

## Planned changes

- `apps/scoreboard/src/scoreboard/scores/models/baseline.py` (new `Baseline` model)
- `apps/scoreboard/src/scoreboard/scores/models/__init__.py` (export, if models are
  re-exported there — confirm during DESIGN)
- `apps/scoreboard/src/scoreboard/scores/migrations/` (new migration for `baselines` table)
- `apps/scoreboard/src/scoreboard/scores/schemas.py` (`BaselineSchema`, `BaselineImportRow`)
- `apps/scoreboard/src/scoreboard/scores/baseline_store.py` (new `BaselineStore`)
- `apps/scoreboard/src/scoreboard/routes/leaderboard.py` (`LeaderboardResponse.baselines`)
- `apps/scoreboard/src/scoreboard/import_baselines.py` (new CLI, mirrors `seed.py`)
- Tests: `tests/unit/scores/test_models.py`, `tests/unit/scores/test_schemas.py`,
  `tests/unit/scores/test_baseline_store.py` (new),
  `tests/unit/test_leaderboard_routes.py`, `tests/unit/test_import_baselines.py` (new)

## Test plan

- Model: table name, FK to `Benchmark` (`on_delete=RESTRICT`), `unique_together`
  (benchmark, model_name, source) enforced.
- Schema: `BaselineSchema`/`BaselineImportRow` validation (accuracy bounds 0-1,
  required fields, `extra="forbid"`).
- Store: `import_baseline` insert + upsert-on-conflict (re-import same
  model_name+source updates in place, doesn't duplicate); `list_baselines` ordering
  (accuracy desc); unknown `benchmark_id` → clear error, no orphan row.
- Route: `GET /v1/leaderboard/{benchmark_id}` returns `baselines: []` when none exist,
  and populated `BaselineSchema` entries when present — existing `entries` behavior
  unchanged (regression check on prior tests).
- Import CLI: JSON-string-in → store-state-out, mirroring `test_seed.py`'s pattern;
  invalid rows handled the same way `seed.py` handles invalid benchmark rows.

## Acceptance

- `GET /v1/leaderboard/{id}` exposes a `baselines` field consumers can read.
- `python -m scoreboard.import_baselines` can idempotently load baseline rows from a
  JSON payload.
- All existing scoreboard tests remain green; new tests cover the above.
- `run_gates.py scoreboard` all green (ruff, format, pyright, pytest --cov-fail-under=80).
- Migration applies cleanly and a second run is a no-op.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned —
  `src/scoreboard/scores/models/baseline.py` (new), `models/__init__.py` (edit),
  `scores/migrations/0002_auto_20260709_1350.py` (new, generated via
  `uv run tortoise makemigrations`), `scores/schemas.py` (edit: `BaselineSchema`,
  `BaselineImportRow`), `scores/baseline_store.py` (new), `main.py` (edit: wire
  `app.state.baseline_store`), `routes/leaderboard.py` (edit: `baselines` field +
  `_baseline_store` helper), `import_baselines.py` (new CLI, mirrors `seed.py`);
  tests: `test_models.py`, `test_schemas.py`, `test_leaderboard_routes.py` (extended),
  `test_baseline_store.py`, `test_import_baselines.py` (new).
- **Commits:** 0582ce6 — feat(scoreboard): import single-model baselines with source attribution
- **Gates:** `run_gates.py scoreboard --skip-append-only` → ALL GATES GREEN (ruff
  check, ruff format --check, pyright 0 errors, pytest 95 passed/1 skipped,
  coverage 87.57% ≥ 80%). Migration applied + re-applied → second run "No migrations
  to apply" (idempotent, per README's verification convention).
- **Deviations:**
  1. `tortoise-dev` companion skill (mandatory per `.claude/sdlc.local.md`
     `companion_skills`) was installed mid-session
     (`tortoise-dev@bershadsky-claude-tools`) but never loaded into this active
     session — plugin loads require a session restart, which wasn't done. Followed
     the same house patterns by reading `models/benchmark.py`/`models/score.py`
     directly (model-per-file, abstract base, native Tortoise migrations, Pydantic
     v2) instead of invoking the skill.
  2. `run_gates.py`'s append-only check (`--base HEAD`) false-positived on
     `test_models.py`/`test_schemas.py`/`test_leaderboard_routes.py` — it flags any
     git-modified test file regardless of content, and can't distinguish a pure
     addition from a rewrite. Verified via `git diff` that all three files only have
     `+` hunks (new imports, new test functions) — zero existing test lines
     altered/removed. Ran with `--skip-append-only` for this cycle. Filed **OME-369**
     to fix the check's heuristic (diff added/removed lines within changed test
     files, not file-level git status).
  3. Scope, per owner decision at ticket start: mechanism only, no real baseline
     data seeded (`hle` is the only benchmark with real external single-model data;
     `livetruth`/`livetruth-latest` are OpenMined-proprietary); portal "target line"
     rendering is an explicit follow-up, not part of this unit.
