---
id: OME-881
linear_url: https://linear.app/openmined/issue/OME-881/screamingface-let-the-per-model-preflight-decide-availability-so
status: in_progress
type: feature
priority: high
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-18
closed:
---

# screamingface: let the per-model preflight decide availability so dynamic admission can trigger

SDK third of `OME-878`, blocked by `OME-880`. The SDK's `/v1/models`-based refusal fires
before the per-model details call that triggers engine-side admission — so OpenRouter-shaped
missing ids now defer to that probe, and the new refusal codes decode into clear
`PlanningError`s. Discovered mid-implementation (the plan assumed an engine preflight that
does not exist).

Ledger: `docs/work/2026-08-18-OME-881-sdk-deferred-availability.md`.
