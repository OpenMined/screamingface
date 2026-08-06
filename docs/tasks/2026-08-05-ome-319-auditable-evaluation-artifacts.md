---
id: OME-319
linear_url: https://linear.app/openmined/issue/OME-319/ome-319-export-a-run-results-per-model-breakdown
status: in_progress
type: Feature
priority: P1
labels: [agentic]
created: 2026-08-05
closed:
---

# OME-319 — auditable Case Results

Retain complete Case Results after the live Engine stream ends. The Engine must preserve exact
input/output, Case Grade, Checks, raw and normalized Evidence, failures, and attributable
provenance. The SDK must expose the same structure through immutable values and machine-readable
Report JSON without interpreting Benchmark-specific semantics.

This refines OME-319 from file-format-only export into the upstream result contract that makes
widgets and JSON/JSONL/CSV export truthful. OME-316 is the related per-Case inspection consumer.
Linear remains unchanged until the owner-approved end-of-stack ticket audit.
