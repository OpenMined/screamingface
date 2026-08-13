---
ticket: OME-694
stack: screamingface
status: in_progress
started: 2026-08-13
finished:
---

# OME-694 — Consume partial benchmark results and graded refusals

## Intent

Complete the Python Client half of OME-807 while keeping the Engine as the only scoring and
failure-policy authority. The Client gains one required top-level coverage value, consumes graded
refusals and partial Candidates, and presents/exports those facts without recomputation.

## Planned changes

- `src/screamingface/report.py` — required immutable Candidate coverage and portable output.
- `src/screamingface/case_result.py` — revised refused Case invariants.
- `src/screamingface/_evaluation/results.py` — exact OME-807 decoding with no inferred coverage.
- `src/screamingface/_ui/report_view.py` — top-level coverage and truthful partial-result copy.
- Public warning surface and README — remove obsolete generic metric coverage policy.
- `tests/` — strict contract, values, report/export, presentation, and evaluation slices.

## Test plan

- Required coverage accepts only finite `[0, 1]` numbers and survives every portable format.
- Graded and grading-failed refusals decode and render with exact text/evidence.
- Numeric Candidate scores retain failed Cases and safe Failures; no-grade results remain
  score-null, zero coverage, and metrics-empty.
- Generic `metrics.coverage` and compatibility shapes are rejected.
- Complete `screamingface` gates green after rebasing onto merged OME-807.

## Acceptance

- One strict Client result interface matches the OME-807 producer wire exactly.
- No Client score, coverage, failure-policy, or sanitization derivation.
- No changes to the user's notebooks or to Engine/Scoreboard production code.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** Client Candidate/Case result values, exact Engine decoder, Report widget,
  public warning exports, README, focused OME-694 tests, and migrated Client fixtures. No Engine,
  Scoreboard production, or notebook files changed.
- **Commits:** one focused OME-694 Client commit; the Git history is the source of its hash.
- **Gates:** 769 passed, 1 skipped; Ruff format/check, Pyright, wheel/sdist build, and distribution
  verification all pass.
- **Deviations:** Prepared from OME-807 commit `599d4510`, then unstacked directly onto merged
  `origin/main` before push/PR. Linear was intentionally left unchanged pending owner approval.
