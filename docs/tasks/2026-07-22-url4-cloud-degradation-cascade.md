---
id: OME-560
linear_url: https://linear.app/openmined/issue/OME-560/degradation-cascade-aiurl4sourcedegraded-reason-codes-coordagentquery
status: backlog
type: decision
priority: P3
labels: [url4-cloud, design-session, agentic]
created: 2026-07-22
closed:
---

# OME-560 — Degradation cascade: ai.url4.source.degraded + reason codes (coord→agent→query)

Kevin requires graceful capability fallback — a node that can't honor an annotation degrades
along `coord=<mode>` → `mode=agent` → `mode=query`, per source, and MUST report each step via
`source.degraded` + a reason code (`coord_mode_unsupported`, `agent_mode_unsupported`, …). Ours
has no capability negotiation or degradation reporting.

**Proposal to prepare:** `ai.url4.source.degraded` CloudEvent + a reason-code registry + a node
capability-advertisement mechanism.

**Open questions:** capability-doc format; interaction with the source-lifecycle events.

design-session — prepare; ratify with Kevin.

Parent: alignment epic (`…-spec-c-alignment`).
