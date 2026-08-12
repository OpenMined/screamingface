---
ticket: OME-793
stack: screamingface
status: in_progress
started: 2026-08-12
finished:
---

# OME-793 — Surface failure identity and failed-state semantics in the report view

## Intent

Debugging the 2026-08-11 HealthBench worst30 fusion run through the report widget required
dropping to raw JSON: the failure banner repeats an identical message with no case ids, a
never-graded case wears the same INCORRECT badge as a genuinely wrong answer, the failed
case's detail pane renders nothing useful, and the withheld metrics show bare dashes with
no reason. All the evidence (case_id, code, collected_errors, failure counts) is already in
`screamingface.report.v1` — this unit makes the view show it. Display-only; the report
artifact and score-withholding rule are untouched.

## Planned changes

- `packages/screamingface/src/screamingface/_ui/report_view.py` — failure banner groups
  identical failures and names cases/codes/underlying errors; tri-state case rendering
  (passed / incorrect / failed) with a distinct warning-styled mark+badge for ungraded
  cases; failed-case pane renders the failures chain and an explicit input-unavailable
  note; unscored candidate card gets a "score withheld — N/M cases failed" warn strip;
  absent-cost cell gets a title distinguishing "not reported" from "withheld".
- `packages/screamingface/tests/test_report_panel.py` — new tests only (append-only).

## Test plan

- RED: banner shows case id + code + first collected error, and collapses 3 identical
  failures into one grouped line (invariant: no failure loses its identity).
- RED: a failed case (grade=None, failures present) renders a `failed` badge distinct from
  `incorrect`, a warning mark in the rail, the failure chain in the pane, and an explicit
  input-unavailable note (invariant: infra failure never presents as a wrong answer).
- RED: an unscored candidate with failed cases explains the dashes ("score withheld — 1/2
  cases failed"); cost `—` carries the not-reported title (invariant: every dash says why).
- Boundaries: single failure (no grouping suffix), failures without case_id/collected
  errors, untrusted text in failure messages stays escaped.
- All prior tests stay green and unmodified.

## Acceptance

- Report of a partially failed run answers in the widget: which cases failed, with what
  code/error, and why aggregate metrics are absent.
- Graded-but-wrong vs never-graded cases visually distinct.
- `run_gates.py screamingface` fully green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `_ui/report_view.py` (banner grouping + `_failure_line` /
  `_first_collected_error` / `_case_state` / `_case_failures_html` / `_withheld_html`,
  warn badge+mark CSS, cost cell title), `tests/test_report_panel.py` (+7 tests,
  append-only).
- **Commits:** single commit on `OME-793-report-failure-ux` (sha in PR).
- **Gates:** ALL GREEN — append-only check, ruff check, ruff format, pyright,
  pytest --cov ≥95 (692 tests: 685+7 −? → suite green), notebook check, uv build,
  distribution check.
- **Deviations:** `report_view.py` was already over the 450-line guidance before this unit
  (629 → ~745 lines); splitting it is out of scope for a display fix — flagged for a
  follow-up refactor rather than done as a drive-by.
