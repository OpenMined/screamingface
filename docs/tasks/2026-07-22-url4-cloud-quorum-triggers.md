---
id: OME-559
linear_url: https://linear.app/openmined/issue/OME-559/quorum-trigger-events-aiurl4trigger-quorum-params
status: backlog
type: decision
priority: P3
labels: [url4-cloud, design-session, agentic]
created: 2026-07-22
closed:
---

# OME-559 — Quorum × trigger events ai.url4.trigger.* + quorum params

Kevin models quorum (quality floor on successfully-resolved sources) × triggers (completeness
thresholds on terminal sources), with `trigger.{fired,result,quorum_unmet,pending}` evaluation
events. Ours has no quorum/trigger concept — the reduce is atomic and opaque.

**Proposal to prepare:** `ai.url4.trigger.*` CloudEvents + a way to carry quorum/trigger protocol
params (`quorum=all|N|majority`, trigger thresholds).

**Open questions:** where params live — query string vs per-expression `;`-annotation (Kevin's
`;cascade` style). Depends on the source-lifecycle work for the terminal/successful counts.

design-session — prepare; ratify with Kevin.

Parent: alignment epic (`…-spec-c-alignment`).
