---
ticket: OME-323
stack: scoreboard
status: in_progress
started: 2026-08-06
finished:
---

# OME-323 — implement open-vs-closed frontier statistics

## Intent

Implements `docs/plan/2026-08-06-open-vs-closed-frontier-stats-plan.md` (built against
`docs/spec/2026-07-16-open-vs-closed-frontier-stats-spec.md`, resolved 2026-07-17,
extended 2026-08-06 with nine follow-up resolutions, currently on unmerged PR #414).
Compute, from real `Score`/`Baseline` rows, what share of a benchmark's accuracy
frontier is held by open-reproducible stacks vs. proprietary ones — both the current
split and the trend over time — and expose it via a new scoreboard API endpoint +
portal stat card.

Starting on Irina Bejan's informal huddle agreement to the nine spec resolutions
(2026-08-06; formal huddle notes pending, PR #414 review still outstanding) — owner
call to proceed with implementation now rather than wait for the formal record.

## Planned changes

- `apps/scoreboard/src/scoreboard/scores/models/score.py`,
  `baseline.py`: `openness_override` column (Phase 0).
- New migration `0004_*.py` (Phase 0).
- `apps/scoreboard/src/scoreboard/scores/schemas.py`: `openness_override` on
  `ScoreSchema`/`BaselineSchema` (Phase 0).
- New `apps/scoreboard/src/scoreboard/classification/{__init__.py,openness.py}`
  (Phase 1).
- New `apps/scoreboard/src/scoreboard/scores/frontier.py` (Phase 2).
- `apps/scoreboard/src/scoreboard/scores/store.py`: `list_all_for_benchmark` (Phase 2).
- `apps/scoreboard/src/scoreboard/scores/schemas.py`: `FrontierResponse` (Phase 3).
- `apps/scoreboard/src/scoreboard/routes/leaderboard.py`: new frontier route (Phase 3).
- `apps/scoreboard/portal/benchmark.html`, `benchmark.js` (Phase 4).

## Test plan

- Phase 0+1 tests written together (Phase 0 is pure additive schema with no
  standalone behavior to test in isolation — Phase 1's override-respecting tests are
  what actually exercise the new column, avoiding a synthetic "column exists"
  assertion): known-open/closed, mixed-provider closed-if-any-closed, unrecognized →
  closed + logged, override wins over the registry in both directions.
- Phase 2: empty benchmark, single score, baseline-in-split-never-in-trend, later-but-
  lower-accuracy not in trend, exact-tie regression, override changes bucket/holder.
- Phase 3: 404 unknown benchmark, empty-benchmark 200, response-shape stability.
- Phase 4: no test harness for the untested vanilla-JS portal page (matches existing
  practice).

## Acceptance

Per plan's Acceptance section (mirrors spec §8, extended).

## Wisdom + confidence review (2026-08-06)

Self-review pass against the complete diff before commit:

- **Empty-providers edge case:** `classify_providers([])` — without the explicit
  early-return, an empty list would fall through the loop with `saw_closed=False`
  and incorrectly return `"open"`. The early return (logged) is load-bearing, not
  redundant; covered by `test_empty_providers_is_closed`.
- **Tie-boundary correctness:** `_compute_trend`'s `score.accuracy <= current.accuracy`
  skip condition uses `<=`, not `<` — confirmed this is what makes an exact tie
  leave the holder unmoved while a strict improvement still advances it. Covered by
  both `test_exact_tie_does_not_move_the_holder` and
  `test_strict_improvement_after_a_tie_does_move_the_holder`.
- **Write-path protection:** `openness_override` is deliberately absent from
  `ScoreSubmission`/`BaselineImportRow` — confirmed a client can't smuggle it in via
  `POST /v1/scores` either, since `ScoreSubmission` keeps `extra="forbid"` and
  `_submission_to_kwargs` lists every kwarg explicitly (no `**payload`
  pass-through). The override is genuinely operator-only, as designed.
- **Route collision check:** `/leaderboard/{benchmark_id}/frontier` (2 path
  segments) vs. the existing `/leaderboard/{benchmark_id}/{spec_id}/history` (3
  segments, literal `history` tail) — confirmed no ambiguity, and the new route's
  own passing tests are empirical proof, not just theoretical.
- **Schema/model change safety:** `openness_override` is nullable with no explicit
  default, matching the existing `content_hash` field's own pattern in this exact
  model — confirmed safe for `Score.create()` calls that don't mention it.

No findings. One round was sufficient — the surface area here (an additive column,
a pure function, one new route, one supplementary portal stat) is much smaller than
OME-404's security-critical auth-boundary work that warranted 4 rounds.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `scores/models/{score,baseline}.py` — `openness_override` column (Phase 0).
  - `scores/migrations/0004_auto_20260806_0000.py` — new migration (Phase 0),
    verified to apply cleanly and idempotently against a throwaway sqlite DB.
  - `scores/schemas.py` — `openness_override` on `ScoreSchema`/`BaselineSchema`;
    new `FrontierPoint`, `FrontierResult`, `FrontierResponse` (Phase 0/2/3).
  - `scores/store.py`, `scores/baseline_store.py` — `openness_override` passthrough
    in `_score_to_schema`/`_baseline_to_schema`; new
    `ScoreStore.list_all_for_benchmark` (Phase 0/2).
  - `classification/{__init__.py,openness.py}` — new (Phase 1).
  - `scores/frontier.py` — new; `compute_frontier` refactored into
    `_current_split`/`_compute_trend` helpers to satisfy `pyright`'s
    too-many-branches lint (Phase 2).
  - `routes/leaderboard.py` — new `GET /v1/leaderboard/{benchmark_id}/frontier`
    (Phase 3).
  - `portal/benchmark.html`, `benchmark.js` — new stat card, fetched independently
    of the main leaderboard call so a failure here never blocks/errors the page
    (Phase 4).
  - Tests: `tests/unit/classification/test_openness.py` (new, 15 cases),
    `tests/unit/scores/test_frontier.py` (new, 7 cases), plus append-only additions
    to `tests/unit/scores/test_store.py` (2 cases) and
    `tests/unit/test_leaderboard_routes.py` (3 cases).
- **Commits:** pending — landing with this ledger update.
- **Gates:** `uv run .claude/scripts/run_gates.py scoreboard --base origin/main
  --skip-append-only` → ruff check ✓, ruff format ✓, pyright (0 errors) ✓, pytest
  155 passed / 2 skipped, coverage ≥80% ✓. Re-run identically under `--python 3.13`
  (fresh venv) → same result.
- **Deviations:**
  1. `--skip-append-only` used, justified: `test_store.py` and
     `test_leaderboard_routes.py` show as git status `M` against `origin/main`
     purely because new tests were appended — confirmed via `git diff | grep '^-'`
     showing zero removed lines in either file. `origin/main` doesn't yet have
     OME-369's line-level append-only fix (still an unmerged PR), so the coarser
     current gate flags any file-level `M` regardless of whether the change is a
     pure addition.
  2. `compute_frontier` was split into `_current_split`/`_compute_trend` helpers,
     not in the original plan text, to satisfy pyright's `PLR0912`
     too-many-branches rule — a mechanical refactor, no behavior change (both
     helpers are exercised by the same tests, which stayed green throughout).
  3. Started on Irina Bejan's informal huddle agreement to the spec's nine
     resolutions (2026-08-06) rather than waiting for the formal huddle notes or
     PR #414's GitHub review — owner's explicit call.
- **Owner-verify:** none beyond the plan's own risk note — PR #414 (the spec) is
  still unmerged, and §10's production data cleanup (the smoke-test row) hasn't
  happened yet, so this feature's first real computation on production will
  currently include that junk row until that separate, explicitly-confirmed cleanup
  action happens.
