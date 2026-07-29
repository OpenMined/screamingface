---
id: OME-625
linear_url: https://linear.app/openmined/issue/OME-625
status: In Progress
type: Feature
priority: P2
labels: [url4-cloud, autonomous, agentic]
created: 2026-07-26
closed:
---

# Add a cached aigateway model-catalog endpoint to url4-cloud

Read-only `GET /v1/models` on the url4-cloud backend, proxied from aigateway's own
`GET /v1/models` and served from a process-wide TTL cache with single-flight and
stale-on-error. Unauthenticated by owner decision (ingress is the trust boundary); the
Runner's `_list_models` is out of scope.

Spec: `docs/spec/2026-07-26-url4-cloud-model-catalog-spec.md`
Plan: `docs/plan/2026-07-26-url4-cloud-model-catalog.md`
Ledger: `docs/work/2026-07-26-OME-625-url4-cloud-model-catalog.md`
