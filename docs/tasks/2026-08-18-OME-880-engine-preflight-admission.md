---
id: OME-880
linear_url: https://linear.app/openmined/issue/OME-880/url4-cloud-preflight-admission-call-runtime-world-overlay-catalog
status: todo
type: feature
priority: high
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-18
closed:
---

# url4-cloud: preflight admission call, runtime world overlay, catalog invalidation

Engine half of `OME-878`, blocked by `OME-879`. On a preflight `routes_for` miss for an
OpenRouter-shaped id, call the gateway `POST /v1/models/admit`. Admitted → in-memory world
overlay + route install (deployment lifetime), catalog ETag invalidated, run proceeds.
Refused → pre-spend `PlanningError` with the gateway's diagnostic code. Admit endpoint
missing/unreachable → today's clean refusal (graceful fallback).

Ledger: `docs/work/2026-08-18-OME-880-engine-preflight-admission.md` (created when the
engine unit starts).
