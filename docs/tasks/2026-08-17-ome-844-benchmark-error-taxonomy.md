---
id: OME-844
linear_url: https://linear.app/openmined/issue/OME-844/split-benchmark-unavailable-into-a-real-error-taxonomy
status: Backlog
type: task
priority: Medium
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-17
closed:
---

# Split benchmark_unavailable into a real error taxonomy

One error code (`benchmark_unavailable`, `benchmarks/evaluation.py`) carries 73 call
sites spanning four distinct failure classes — genuine asset/infra unavailability,
protocol/contract violations, check-judge runtime failures, and benchmark-definition
bugs — all `permanent=True`. The client/report cannot branch on cause and telemetry
cannot aggregate it.

Fix: keep `benchmark_unavailable` for asset/infra only; add
`benchmark_contract_violation`, `check_judge_failed`, `benchmark_definition_invalid`;
reclassify the 73 sites (messages verbatim); set `permanent` per class. Wire-compat
check first (nothing may pin the old code string).

Out of scope: url4-core `finish_reason` plumbing; gateway `reasoning_effort` support.

Full problem statement, evidence, and Before/After: the Linear issue body.
