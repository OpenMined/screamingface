---
id: OME-934
linear_url: https://linear.app/openmined/issue/OME-934/expose-generic-run-scoped-structured-log-seam
status: in_progress
type: improvement
priority: 2
labels: [screamingface-engine, agentic, autonomous]
created: 2026-08-22
closed:
---

# Expose generic run-scoped structured Log seam

Add one optional injected Runner run scope that receives the exact rendered URL4 and an opaque
structured-Log emitter backed by the existing bridge.

The seam is generic, fail-open, concurrency-isolated, and contains no Benchmark or progress
semantics. It changes neither generated URL4 nor `packages/url4`. OME-932 is its first consumer
and lands in a separate PR.
