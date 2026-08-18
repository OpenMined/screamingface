---
id: OME-878
linear_url: https://linear.app/openmined/issue/OME-878/run-any-openrouter-model-dynamic-admission-at-preflight
status: in_progress
type: epic
priority: high
labels: [aigateway, agentic, autonomous]
created: 2026-08-18
closed:
---

# Run any OpenRouter model: dynamic admission at preflight

Cross-cutting epic (aigateway + url4-cloud). When a run asks for an OpenRouter model the
engine doesn't know, the engine asks the gateway "does this model actually exist on
OpenRouter?" The gateway checks OpenRouter's public model list. Real → admitted on the fly
(in-memory, deployment lifetime) and the run just works. Typo / disabled / uncredentialed →
clear refusal before any money is spent.

Plan: `.dk/plans/2026-08-18-openrouter-dynamic-model-admission.md` (Khoa-approved
2026-08-18). Sub-issues: `OME-879` (gateway admit endpoint), `OME-880` (engine preflight +
world overlay, blocked by 879).
