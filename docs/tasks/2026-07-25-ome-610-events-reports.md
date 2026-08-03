---
id: OME-610
linear_url: https://linear.app/openmined/issue/OME-610/implement-typed-events-and-reports
status: blocked
type: feature
priority: high
labels: [py-screamingface, agentic, autonomous]
created: 2026-07-25
closed:
---

Implement Slice 4 of the approved OME-605 Client v1 plan: typed Events and one immutable Report
shape for one or many independently executed Candidates. The public values are implemented;
terminal decoding is blocked on the Ionesio-owned SF Engine Candidate Result and Operation/Event
attribution contracts.

Candidate usage is an inclusive, potentially overlapping comparison value. Report usage must use
an authoritative Engine-provided Evaluation total rather than summing Candidates. Rich token,
per-type cost, pricing/cache provenance, and saved-cost fields remain blocked on OME-617/OME-618;
timing stays separate from usage.
