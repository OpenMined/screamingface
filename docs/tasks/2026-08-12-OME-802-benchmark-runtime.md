---
id: OME-802
linear_url: https://linear.app/openmined/issue/OME-802/extract-generic-benchmark-outcome-and-scoring-runtime-in-url4-cloud
status: Done
type: Feature
priority: P1
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-12
closed: 2026-08-13
---

# Extract generic benchmark outcome and scoring runtime in URL4 Cloud

Replace the shallow Candidate Result envelope and per-Benchmark result dictionaries with one
strict producer contract and fail-closed finalization module shared by DRACO, IFEval, and
HealthBench. Preserve complete Engine-owned URL4 and keep benchmark-specific checking and scoring
semantics behind small adapters.

Spec: `docs/spec/2026-08-12-OME-802-benchmark-runtime.md`
Plan: `docs/plan/2026-08-12-OME-802-benchmark-runtime.md`
Ledger: `docs/work/2026-08-12-OME-802-benchmark-runtime.md`
