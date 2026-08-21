---
ticket: OME-922
stack: screamingface
status: in_progress
started: 2026-08-20
finished:
---

# OME-922 — Warn that partial-submission scores are not directly comparable

## Intent

Prevent a user from mistaking a limited or incompletely graded benchmark submission for a
score directly comparable with a full run. The Client warns at the submission seam but
preserves the existing advisory-only behavior and sends valid partial scores unchanged.

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

- **Actual files:** task/spec/plan/work records and the SDK README; the Scoreboard adapter plus
  focused submission-notice policy; shared environment and notice values; standalone notebook
  notice presentation; Candidate Result serialization; and focused notice, public-workflow,
  Report, and environment tests. The abandoned score-field/card CSS/global-palette approach is
  removed from the final diff.
- **Commits:** the original implementation/policy/presentation series through `44f3d31e`, plus
  `c6f3b9a2 fix(screamingface): make partial notices follow documented workflows`.
- **Gates:** every reviewer reproduction first failed at its public seam, then passed. The final
  public-workflow module has 14 tests. A clean temporary merge with current `origin/main`
  collected 1,006 tests and passed the complete official stack: Ruff check/format, Pyright,
  1,005 pytest passes with one skip and the 95% coverage floor, deterministic notebook check,
  build, and distribution verification.
- **Deviations:** a fresh worktree needs the declared `uv sync --extra notebook` before Pyright
  can resolve IPython/ipywidgets. The integrated append-only check was skipped because current
  main's already-landed PR #607 changes `test_runtime_cli.py` relative to this older PR head; the
  final OME-922 diff restores `test_leaderboards.py` exactly to main, adds one focused test file,
  and only appends tests elsewhere. Four locally executed notebooks remain user-owned unstaged
  changes and were not regenerated, staged, or overwritten.

## Brand presentation follow-up

The first implementation correctly warned but Jupyter rendered the `UserWarning` as a
large red, path-heavy block above a successful green receipt. Reopen this task to move the
advisory into the notebook score card, while retaining a Python warning in headless code.
Use the canonical persimmon warning tokens and square status treatment from
`OpenMined/screamingface-brand` commit `7ea35a1`. The four locally executed example
notebooks are user-owned working-tree changes and must remain untouched.

### Follow-up outcome

- Notebook submissions now carry a `Partial submission` status notice inside the published
  score card and do not emit a duplicate Python warning; headless sync and async callers
  retain the warning.
- The notice uses the canonical persimmon light/dark tokens, solid status square, square
  edges, and no decorative effects from brand commit `7ea35a1`.
- RED was confirmed by two missing notebook-carrier failures. The complete leaderboard
  module passes 52 tests.
- The official gate suite is fully green from a clean worktree: append-only, Ruff check and
  format, Pyright, full pytest with the 95% coverage floor, notebook check, build, and
  distribution check. The first clean-worktree attempt required the repository's declared
  `notebook` extra before Pyright could resolve IPython and ipywidgets.

## Policy correction follow-up

Review established that the Scoreboard does not currently exclude partial submissions from
ranking. The notice now states the behavior that exists: a partial score may appear on the
public leaderboard, but because it is based on fewer benchmark Cases it is not directly
comparable with a full-run score. Full-coverage-only ranking remains separate Scoreboard policy
scope.

## Review correction follow-up

Review found that the headless warning skips past the user's submission frame. Review also
surfaced an ambiguity between the Report-rendering non-goal and the intentional shared
persimmon warning-token migration; the owner confirmed that every warning surface should use
the brand-accurate palette.

### Planned changes

- Append a regression proving a headless warning is attributed to the caller.
- Correct the warning stack level without changing submission or response behavior.
- Clarify that the shared Report warning-palette correction is intentional and preserve it.
- Correct semantic comment anchors and bring this ledger's outcome up to date.

### Test plan

- RED: the warning-origin regression observes the current synthetic `<sys>` location.
- GREEN: the same regression points to the caller after the stack-level correction.
- Regression: submission payload, notebook carrier, shared Report tokens, sync/async behavior,
  and all existing tests remain correct.
- Run the complete official `screamingface` gate suite from a clean worktree.

### Review correction outcome

- The documented `sf.leaderboards.submit()` facade now skips every SDK frame rather than relying
  on one fixed `stacklevel`; three submissions on three user lines produce three independently
  attributed `sf.EvaluationWarning` values with exact copy.
- Headless advisories run before the POST, so warnings-as-errors cannot persist a score and then
  hide its id. Sync and async behavior are covered independently.
- Notebook submissions explicitly publish one branded display event after success, including
  assignment, lists, papermill, and nbconvert. The returned score remains unchanged, final
  expressions do not repeat the notice, failed POSTs display nothing, and a broken display
  publisher falls back to stderr without hiding an already persisted id.
- Exported Candidate Results retain the full Benchmark Case count while the Report root retains
  the selected count, so the documented saved-result loader still identifies a limited run.
- Colab and Databricks shells are recognised through their ipykernel base class.
- Persimmon is scoped to the new submission notice; existing Report warnings keep their distinct
  amber palette. Severity is visible in the class/data contract and warning notices use
  `role="alert"`.
- The weak test block was replaced by a focused public-workflow module. Exact strings are compared
  literally, notice existence is asserted from captured display output, palette tests are
  independent of behavior tests, and warning filters are scoped to `sf.EvaluationWarning`.
- The task mirror and ledger remain `in_progress` together until review and merge.
