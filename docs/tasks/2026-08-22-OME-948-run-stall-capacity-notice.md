---
id: OME-948
linear_url: https://linear.app/openmined/issue/OME-948/surface-a-generic-capacity-warning-when-a-runner-job-cannot-be
status: in_progress
type: improvement
priority: 2
labels: [screamingface-engine, agentic, autonomous]
created: 2026-08-22
closed:
---

# Surface a generic capacity warning when a Runner Job cannot be scheduled

When a Runner Job is accepted but its Pod can never be created (the `sf-fusion` `ns-ceiling`
quota — OME-947 — or any other scheduling refusal), the run stalls silently for up to 16h with
no user-visible signal. The Engine detects a Job stuck in `scheduled` past a grace window and
sends one generic `warn` notice to the run's attached client through the existing notice
channel, and maps schedule-time Kubernetes API failures from a naked 500 to a generic retryable
503.

Canonical artifacts:

- Spec: `docs/spec/2026-08-22-OME-948-run-stall-capacity-notice.md`
- Plan: `docs/plan/2026-08-22-OME-948-run-stall-capacity-notice.md`
- Ledger: `docs/work/2026-08-22-OME-948-run-stall-capacity-notice.md`
