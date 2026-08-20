---
ticket: OME-922
stack: screamingface
status: done
started: 2026-08-20
finished: 2026-08-20
---

# OME-922 — Warn that partial submissions are not ranked

## Intent

Prevent a user from mistaking a limited or incompletely graded benchmark submission for a
rankable full run. The Client warns at the submission seam but preserves the existing
advisory-only behavior and sends valid partial scores unchanged.

## Planned changes

- `packages/screamingface/tests/test_leaderboards.py` — append sync/async warning coverage.
- `packages/screamingface/src/screamingface/_scoreboard/leaderboards.py` — emit the warning
  from the shared submission builder.
- Add the required task, spec, plan, and work records for `OME-922`.

## Test plan

- RED: limited run warns while still POSTing.
- RED: full-sized but incompletely graded run warns while still POSTing.
- Boundary: a complete full run emits no warning.
- Parity: asynchronous submission behaves identically.
- Regression: payload and existing validation remain unchanged.

## Acceptance

- Both limited and incompletely graded valid submissions show the exact ticket warning.
- Full submissions remain silent.
- Warnings never block the POST or change its payload.
- All `screamingface` gates pass.

## Outcome

- **Actual files:** the shared Client Scoreboard adapter, append-only leaderboard tests, and
  the task/spec/plan/work records listed above.
- **Commits:** this commit — `fix(screamingface): warn on partial leaderboard submissions`.
- **Gates:** RED confirmed three missing-warning failures; focused suite 49 passed; 959 tests
  collected; official `run_gates.py screamingface` completed with ALL GATES GREEN (append-only,
  Ruff check/format, Pyright, full pytest with 95% coverage floor, notebook check, build, and
  distribution check).
- **Deviations:** the fresh worktree needed `uv sync --extra notebook` before Pyright could
  resolve the declared notebook dependencies. The first green test refactor touched inherited
  fixture lines; the append-only gate rejected it, so those lines were restored and all new
  fixtures/tests were appended. No gate was skipped and no inherited test remains changed.
