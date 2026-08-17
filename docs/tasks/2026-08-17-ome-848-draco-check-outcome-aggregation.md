---
id: OME-848
linear_url: https://linear.app/openmined/issue/OME-848/aggregate-dracos-5-pass-verdicts-into-check-outcomes-and-render
status: Backlog
type: bug
priority: Medium
labels: [url4-cloud, py-screamingface, agentic, autonomous]
created: 2026-08-17
closed:
---

# Aggregate DRACO's 5-pass verdicts into check outcomes; render missing outcomes as unjudged

DRACO's check builder (`benchmarks/draco/case_results.py`) ships 5 raw evidence
verdicts per criterion but never fills the top-level `outcome`, and the report view
paints a missing outcome as "bad" — so every positive criterion renders red and every
negative green, verdict-blind, and every DRACO case chips INCORRECT. Scores were
always correct; presentation lied.

Fix: engine sets `outcome` = majority of valid passes (absent on no-valid/tie);
UI renders outcome-less checks as neutral "unjudged" and excludes them from the case
verdict. Case-chip binary for rubric benchmarks = open design question in the issue.
Out of scope: HealthBench points-sign vocabulary mismatch (separate ticket).

Full evidence and Before/After: the Linear issue body.
