---
ticket: OME-633
stack: url4
status: in_progress
started: 2026-07-27
finished:
---

# OME-633 — typecheck error in test_observe.py keeps the url4 CI gate red

## Intent

The `url4 Tests` workflow has been failing on `OME-587-url4-cloud-engine-integration` since
before the branch was rebased (red on `4bbfce61`, `8fb844d2`, `315c4502`, and again on the
post-rebase `5897490a`). The base branch `OME-513-url4-cloud` (PR #419) is fully green, so
the defect is this branch's own and it blocks PR #425.

A single pyright error, in the observation-seam test file that landed with [[OME-446]]
(commit `e3affad2`):

```
packages/url4/tests/unit/test_observe.py:303:23 - error: Argument of type "object"
  cannot be assigned to parameter "target" of type "Node | str | Graph | DagNode"
  in function "run"
1 error, 0 warnings, 0 informations
```

`test_observe.py:246` annotates the corpus as `_CORPUS: list[object]` because it mixes
expression strings with a hand-built `_BoomNode()`. At line 303 that widened element type
reaches `run(target: str | AstNode | Graph | DagNode, ...)` (`src/url4/dag/executor.py:310`)
and `object` satisfies none of the union members.

**The red X is worse than it looks.** `Typecheck` runs BEFORE the test step
(`.github/workflows/url4-tests.yml:55` vs `:58`), so the job dies without ever invoking
pytest. The 677-test url4 suite has not run in CI on this branch at all — the failure hides
an *unexecuted* suite, not a failing one.

## Planned changes

- `packages/url4/tests/unit/test_observe.py` — import `DagNode` from `url4.dag.node`;
  widen-correctly `_CORPUS: list[object]` → `_CORPUS: list[str | DagNode]`.

No production code. `_BoomNode` structurally satisfies the `DagNode` Protocol
(`src/url4/dag/node.py:84`, `@runtime_checkable`), so naming the real type is sufficient —
no `cast`, no `type: ignore`, no change to `run`'s signature.

## Test plan

TDD's RED step is supplied by the gate itself rather than a new test: **pyright is the failing
check**, reproduced locally at `1 error` before the change and `0 errors` after. Writing a test
to assert an annotation would test pyright, not url4.

The existing suite is the regression guard, and it matters here specifically because it had
never run under this gate: the fix is only correct if all 677 tests still execute and pass
with the corpus typed.

## Acceptance

- `uv run pyright` → 0 errors in `packages/url4`.
- `uv run ruff check` + `ruff format --check` clean.
- url4 suite executes and is green (677 passed).
- `url4 Tests` green on both 3.12 and 3.13, unblocking PR #425.

## Outcome

- **Actual files:** as planned — `packages/url4/tests/unit/test_observe.py` only (+2/−1).
- **Commits:** see the OME-633 commit on `OME-587-url4-cloud-engine-integration`.
- **Gates:** `run_gates.py url4 --skip-append-only` — **ALL GATES GREEN** (ruff check · ruff
  format · pyright · pytest+coverage vs the 95% floor). Suite **677 passed**.
- **Deviations:**
  - **The append-only test gate was consciously overridden** (`--skip-append-only`). Rule 5
    flags any `M` on a prior test path, and this fix cannot avoid one: the defect *is* a type
    annotation on `_CORPUS`, a module-level constant inside the existing
    `test_observe.py`. There is no new-file form of it — the house workaround used in
    [[OME-623]] (put new behaviour in a self-contained new test file) does not apply to
    correcting a declaration in place. The hazard rule 5 guards against — weakening a prior
    test so the suite goes green — is absent here: the diff is +2/−1, touches zero
    assertions, zero fixtures and zero test bodies, and all 677 pre-existing tests still
    pass unchanged. Recorded rather than silently skipped, per the Confidence Gate.
  - One environment finding, not a code change: this
  worktree's `packages/url4/.venv` still carried stale absolute shebangs from the
  `url4-integration` rename, so `conftest.py` could not import `url4` at all and no local
  test run was trustworthy until `rm -rf .venv && uv sync --all-extras`. Same root cause
  recorded in [[OME-623]]/[[OME-624]] — third occurrence, now on the `url4` stack rather
  than `url4-cloud`.
