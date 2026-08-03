---
id: OME-618
linear_url: https://linear.app/openmined/issue/OME-618/publish-candidate-result-and-operation-attributed-event-contracts
status: blocked
type: contract
priority: high
labels: [screamingface-engine, human, design-session]
parent: OME-614
blocked_by: [OME-616, OME-617]
blocks: [OME-610, OME-297]
related: [OME-303, OME-314, OME-446, OME-558, OME-587]
created: 2026-07-26
closed:
---

Publish the typed Candidate Result schema and SF operation-attribution extension carried by the
existing url4-cloud CloudEvents lifecycle.

The Client combines the Engine result body, lifecycle evidence, and inspected Candidate into one
typed Candidate Result; it never grades, aggregates, calculates scores, or invents missing usage.

Reuse the generic URL4 Cloud `ai.url4.cost.usage` taxonomy for token and per-type USD accounting,
`self`/`subtree` scope, and pricing provenance. SF attribution joins each Event to its static
operation and dynamic Case/Judge/Tool occurrence. Successful Runs publish authoritative Candidate
totals; Case-attributed work remains available for detailed artifacts without allocating
benchmark-wide aggregation work across Cases.
