---
id: OME-508
linear_url: https://linear.app/openmined/issue/OME-508/url4-enforce-mandatory-intent-on-expression-groups-and-iteration
status: Done
type: Improvement
priority: 2
labels: [url4-engine, autonomous, agentic]
created: 2026-07-20
closed: 2026-07-20
---

# url4: enforce mandatory intent on expression groups and iteration bodies

Part of the `OME-500` conformance epic. Owner ruling: intent-less parenthesized
groups ("bare groups") and intent-less iteration bodies are not part of the
grammar — enforce at the parse/render/builder boundary, DAG machinery untouched.
Exempt per the grammar: `paren-collection` (`(…)` followed by `*(`), structured
weights/budgets, struct objects. Exempt per owner choice: non-parenthesized
fragment roots. Ledger: `docs/work/2026-07-20-OME-508-url4-mandatory-intent.md`.

> Owner action pending (same as `OME-507`): the `pkg/url4-python-sdk` landing
> label could not be attached via the CLI — add it in the Linear UI.
