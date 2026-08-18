---
ticket: OME-833
stack: url4-cloud
status: done
started: 2026-08-14
finished: 2026-08-14
---

# OME-833 — Raise the local-mode concurrent run ceiling above the Client fan-out

## Intent

Local mode refuses a Run with `503 the runner is at capacity — retry shortly` too early. The
in-process runner accepts 8 Runs at the same time, and the Client starts up to 8 Runs at the
same time. The two limits are equal, so there is no spare capacity. Any extra Run fails,
including an abandoned Run that holds its slot for up to 16 hours. This unit increases the
local ceiling to 32 and adds a test that keeps the ceiling above the Client fan-out.

## Planned changes

- `apps/url4-cloud/tests/unit/test_inprocess_runner.py` — add the floor test (RED first)
- `apps/url4-cloud/src/url4_cloud/adapters/inprocess.py` — `DEFAULT_MAX_CONCURRENT_RUNS` 8 to 32
- `apps/url4-cloud/src/url4_cloud/config.py` — `local_max_concurrent_runs` 8 to 32, and comment

## Test plan

- The floor test asserts that both url4-cloud constants exceed the Client fan-out of 8. It
  fails first, because both are 8.
- The existing capacity tests still pass. `test_inprocess_runner.py:248` and `:263` pass an
  explicit `max_concurrent_runs`, so they do not depend on the default.
- The existing local app test at `test_local_app.py:84` passes an explicit
  `local_max_concurrent_runs=3`, so it does not depend on the default.

## Acceptance

- Both url4-cloud constants read 32.
- The floor test fails if the ceiling drops to 8 or lower.
- `uv run .claude/scripts/run_gates.py url4-cloud` passes.

## Notes

`apps/url4-cloud` does not depend on `packages/screamingface`, so the test cannot read
`_MAX_CANDIDATES_IN_FLIGHT` directly. The test asserts a documented floor instead and names the
Client constant in its rationale. The spec records the two rejected alternatives.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `apps/url4-cloud/tests/unit/test_local_capacity_contract.py` — NEW (planned as an addition to
    `test_inprocess_runner.py`; see Deviations)
  - `apps/url4-cloud/src/url4_cloud/adapters/inprocess.py` — `DEFAULT_MAX_CONCURRENT_RUNS` 8 → 32,
    plus the INVARIANT anchor naming the Client fan-out
  - `apps/url4-cloud/src/url4_cloud/config.py` — `local_max_concurrent_runs` 8 → 32, plus the
    WHY-32 rationale
  - `docs/spec/2026-08-14-OME-833-local-run-ceiling.md`, `docs/plan/…`, `docs/tasks/…` — artifacts
- **Commits:** `fix(url4-cloud): raise the local concurrent run ceiling above the Client fan-out`
  (sha recorded in the OME-833 close comment). `fix` rather than `feat`: this resolves spurious
  503s, so release-please should cut a patch.
- **Gates:** `run_gates.py url4-cloud` → ALL GATES GREEN — append-only test check, ruff check,
  ruff format --check, pyright, check_layering.py, pytest with coverage ≥80. Full suite
  **1415 passed, 5 skipped**.
- **Deviations:**
  - The floor test went into a NEW module `tests/unit/test_local_capacity_contract.py` instead of
    into `test_inprocess_runner.py`. That module carries a module-level `pytestmark =
    pytest.mark.asyncio`, which makes pytest warn on the two synchronous constant assertions. The
    separation is also truer to what the tests are: a cross-distribution contract about where the
    ceiling is set, not runner behaviour when it is reached. `test_inprocess_runner.py` is
    unmodified.
  - No other deviation. Both constants read 32; the guard fails at 8 or below.
