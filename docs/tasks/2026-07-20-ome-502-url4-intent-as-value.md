---
id: OME-502
linear_url: https://linear.app/openmined/issue/OME-502
status: Done
type: Bug
priority: P1
labels: [url4-engine, pkg/url4-python-sdk, autonomous, agentic]
created: 2026-07-20
closed: 2026-07-20
---

# OME-502 — Honor intent = value

intent_atom recognises only 4 shapes, flattening nested expressions, struct-objects, var-refs and self-refs to Text. A nested-expression intent is never compiled into a subgraph — it reaches the model as literal prompt text.

Parent epic: `OME-500`. Full audit findings live in the Linear description.
