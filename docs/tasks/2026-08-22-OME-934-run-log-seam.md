---
id: OME-934
linear_url: https://linear.app/openmined/issue/OME-934/expose-generic-run-scoped-structured-log-seam
status: in_review
type: improvement
priority: 2
labels: [screamingface-engine, agentic, autonomous]
created: 2026-08-22
closed:
---

# Expose generic run-scoped structured Log seam

Add one optional injected Runner run scope that receives the exact rendered URL4 and an opaque
structured-Log emitter backed by the existing bridge.

The seam is generic, fail-open, and concurrency-isolated. OME-934 also wires one dormant
`BenchmarkRegistry` adapter and task-local recorder through the production composition root, while
keeping generic executor code free of Benchmark imports. It publishes no progress schema or
semantic record. It changes neither generated URL4 nor `packages/url4`; OME-932 adds terminal Case
and provisional-score semantics under `benchmarks/*` in a separate PR.
