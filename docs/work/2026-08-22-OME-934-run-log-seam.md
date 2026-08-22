---
ticket: OME-934
stack: screamingface-engine
status: in_progress
started: 2026-08-22
finished:
---

# OME-934 — expose generic run-scoped structured Log seam

## Intent

Specify the smallest generic Runner port needed for observational features to emit structured Logs
without importing their domain semantics into Runner code, and finish its production composition
through one dormant Benchmark adapter so the first consumer requires no second core change.

## Planned changes

- `docs/spec/2026-08-22-OME-934-run-log-seam.md`
- `docs/plan/2026-08-22-OME-934-run-log-seam.md`
- one dependency-free generic port, local structured-Log bridge input, and Runner lifecycle
  implementation
- one task-local Benchmark recorder and registry adapter wired only at the composition root
- focused isolation, ordering, failure, composition, regression, and layering tests

## Test plan

- RED tests for exact URL4 handoff, same-bridge Log delivery, scalar validation, nested/concurrent
  isolation, ownership refusal, expired emitters, and fail-open setup/emission/teardown.
- Production `build_executor` proof for the wired but semantically dormant Benchmark adapter.
- Regression fixtures for unchanged result, URL4 identity, existing Events, errors, cancellation,
  early consumer exit, bridge pressure, and world teardown.
- Layering test allowing the concrete adapter only at the composition root.

## Acceptance

- No Benchmark schema or semantics in generic Runner modules.
- No `screamingface.evaluation-progress.v1` records in OME-934.
- No generated URL4 or `packages/url4` change.
- Owner approved the revised specification, plan, and implementation on 2026-08-22 before
  production code began.

## Follow-up iteration — review hardening

### Intent

Close the approved PR review findings without expanding the seam: preserve exact scalar meaning,
make its event-loop affinity enforceable, state standard failed-entry cleanup ownership, keep
documentation and exports honest, and make the layering guard recursive.

### Planned changes

- Reject `nan` and positive/negative infinity as malformed structured-Log attributes.
- State and enforce that the emitter may run only on its owning event-loop thread.
- Document that a returned context manager must unwind partial acquisition inside a failing
  `__enter__`, because the Runner will not call `__exit__` afterward.
- Correct root-versus-span log documentation and align `runner.run_logs.__all__` with its public
  names.
- Recursively guard the complete Runner tree against concrete Benchmark-adapter imports.

### Test plan

- RED parametrized wire-seam tests for all non-finite float values and whole-record rejection.
- RED cross-thread submission test proving the record is dropped without touching the bridge.
- RED contract/export assertions and a nested Runner-package layering fixture.
- Focused run-log suites, then the complete `screamingface-engine` quality gate.

### Acceptance

- Invalid or off-thread submissions remain observational and cannot change execution.
- The generic port carries every lifecycle/threading constraint an adapter author must know.
- Existing URL4 Logs, wire types, bridge ordering, and Benchmark behavior remain unchanged.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added the dependency-free port in
  `apps/screamingface-engine/src/screamingface_engine/run_log_contract.py`; generic lifecycle,
  validation, expiry, and bridge delivery in `runner/run_logs.py` + `runner/executor.py`; the
  task-local registry adapter in `benchmarks/run_logs.py`; production composition in
  `runner/main.py`; 22 focused behavioral tests across `test_run_log_seam.py` and
  `test_benchmark_run_logs.py`; and the approved spec/plan/task/work artifacts.
- **Commits:** `83d9de64` — `docs: finalize OME-934 run log seam design`; `f204d2df` —
  `feat(screamingface-engine): add generic run Log scope`; the Benchmark adapter, production
  wiring, and this outcome land in this branch's final implementation commit.
- **Gates:** focused generic suite 55 passed; focused adapter/composition/regression suite 132
  passed; `python3 .claude/scripts/run_gates.py screamingface-engine` passed Ruff check, Ruff
  format, Pyright, layering, append-only verification, and the complete coverage suite twice.
- **Deviations:** the dependency-free factory/emitter/scalar port vocabulary moved from the Runner
  implementation module into an app-owned shared leaf after the layering gate correctly rejected
  a Benchmark adapter importing `screamingface_engine.runner`. Runner lifecycle implementation
  remains in `runner/run_logs.py`; no scope or external contract changed.

### Follow-up outcome

- **Actual files:** hardened scalar and thread-affinity validation in `runner/run_logs.py`; made
  adapter lifecycle requirements explicit in `run_log_contract.py` and the approved spec; corrected
  root/log-like documentation in `runner/executor.py`; and appended finite-value, cross-thread,
  export, and recursive-layering coverage to the two existing OME-934 test modules.
- **Tests:** each behavioral change was observed RED before implementation; the complete focused
  run-log suite passed with 28 tests.
- **Gates:** `python3 .claude/scripts/run_gates.py screamingface-engine` passed append-only
  verification, Ruff check, Ruff format, Pyright, layering, and the complete coverage suite.
- **Deviations:** the append-only gate refused an in-place strengthening of the existing flat
  layering test, so that test remains byte-identical and a separate recursive guard now covers the
  complete Runner tree. No production scope or contract was weakened.
- **Commit:** the follow-up hardening lands in this branch's next `fix(screamingface-engine)`
  commit with `Refs: OME-934`.
