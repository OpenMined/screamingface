---
id: OME-617
linear_url: https://linear.app/openmined/issue/OME-617/publish-evaluation-scoped-shared-work-and-cache-provenance-contract
status: queued_next
type: contract
priority: high
labels: [screamingface-engine, human, design-session]
parent: OME-614
blocks: [OME-609, OME-610, OME-297]
related: [OME-304, OME-305, OME-306, OME-311, OME-344]
created: 2026-07-26
closed:
---

Publish Evaluation-scoped shared-work identity, scheduling, independence, failure propagation,
and cache-provenance semantics across independently executed flat Candidate URL4s.

The contract must reproduce shared DRACO panel answers while keeping equal-looking independent
samples and Judge passes distinct, without multi-root URL4 or direct Client-to-AI-Gateway calls.

Each physical provider dispatch owns one authoritative usage record. Candidate inclusive totals
may reference overlapping shared work and are therefore non-additive; the Evaluation billed total
de-duplicates physical dispatches. The Engine never allocates a shared call to the first requester,
and it reports billed and saved cost separately for persistent cache hits and in-flight joins.
