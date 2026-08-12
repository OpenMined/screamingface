---
id: OME-793
linear_url: https://linear.app/openmined/issue/OME-793/surface-failure-identity-and-failed-state-semantics-in-the-report-view
status: in_progress
type: bug
priority: high
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-12
closed:
---

# Surface failure identity and failed-state semantics in the report view

The report widget discards failure evidence the report already carries: banner lines with
no case ids, INCORRECT badges on never-graded cases, "None" detail panes, unexplained
metric dashes. Display-only fix in `_ui/report_view.py`; scope and Before/After in Linear.
Ledger: `docs/work/2026-08-12-OME-793-report-failure-ux.md`. Related: `OME-784`, `OME-794`.
