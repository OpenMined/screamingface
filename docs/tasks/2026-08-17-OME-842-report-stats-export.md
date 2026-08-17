---
id: OME-842
linear_url: https://linear.app/openmined/issue/OME-842/export-per-member-and-per-axis-stats-artifacts-from-a-saved-report
status: Backlog
type: Feature
priority: P3
labels: [py-screamingface, agentic, deferred]
created: 2026-08-17
closed:
---

# Export per-member and per-axis stats artifacts from a saved Report

The legacy benchmarks pipeline saved per-run stats tables (by model/axis/judge/mode),
plots, and snapshots. `report.v1` carries none of these derived views. Once `OME-784`
(per-operation outputs + snapshots) and `OME-699` (member usage/timing attribution) put
raw per-member data into the report, add a client-side, read-only export that derives the
legacy-parity artifacts from any saved Report: standard stats tables, plots, and a tabular
judge-evidence dump.

Blocked-by: `OME-784`, `OME-699` (hence `deferred`). Related: `OME-488`.

Source of truth: legacy `screamingface-benchmarks` saved-outputs layout
(`draco/<run>/{stats,visual_plots,metrics}`) for artifact shapes; `report.v1`
(`packages/screamingface/src/screamingface/report.py`) for the input contract.
