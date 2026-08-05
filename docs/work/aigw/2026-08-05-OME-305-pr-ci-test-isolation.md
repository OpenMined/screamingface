---
ticket: OME-305
stack: aigateway
status: done
started: 2026-08-05
finished: 2026-08-05
---

# OME-305 — isolate the global-cache purity probe from pytest

## Intent

Keep the global-cache projection purity test hostile to ambient I/O without letting its
temporary patches affect pytest's own verbose progress output, coverage reporting, or JUnit XML
writer after the test body returns.

## Planned changes

- `apps/aigateway/tests/unit/test_global_cache_projection_purity.py` — scope the stdlib and
  environment poison with `MonkeyPatch.context()` so it is undone before pytest reports the test.
- `docs/work/aigw/2026-08-05-OME-305-pr-ci-test-isolation.md` — record RED/GREEN and gate evidence.

## Test plan

- RED: reproduce the GitHub Actions failure with verbose output, coverage, and `--junitxml`.
- GREEN: rerun that exact focused command and confirm pytest writes both reports successfully.
- Run the complete AIGateway gate with the existing OME-305 append-only supersession.

## Acceptance

- The purity probe still raises if a provider projection reads the clock, randomness, filesystem,
  or environment.
- Pytest can emit verbose progress, coverage XML, and JUnit XML after the probe completes.
- The complete AIGateway gate is green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** the planned purity test and this ledger only; no production, dependency, or
  configuration files changed.
- **Commits:** this remediation commit — `fix(aigateway): isolate global cache purity test`
  (`Refs: OME-305`).
- **Gates:** the exact CI-shaped focused command reproduced RED on branch-pinned pytest 9.0.3,
  failing after the test body passed when verbose reporting read `os.environ['COLUMNS']` and JUnit
  XML called `open`; after the fix the same command completed `1 passed` and wrote coverage/JUnit
  XML. `uv run .claude/scripts/run_gates.py aigateway --base origin/main --skip-append-only` ended
  `ALL GATES GREEN` (ruff check, ruff format, pyright, Enterprise import guard, full pytest with
  coverage).
- **Deviations:** none. The existing test changed under the OME-305 supersession because the defect
  is its patch lifetime; the projection-purity assertions and poisoned ambient sources are unchanged.
