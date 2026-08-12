---
id: OME-779
linear_url: https://linear.app/openmined/issue/OME-779/report-cache-entry-age-and-accept-a-max-age-control
status: Backlog
type: Feature
priority: P2
labels: [aigateway, agentic, autonomous]
created: 2026-08-11
closed:
---

# Report cache entry age and accept a max-age control

Phase 1a, the gating phase of OME-777. Emit an Age header on cache hits, widen the deliberately-closed cache-control grammar to accept max-age alongside use-cache, honour that bound on read, and set expires_at via a configurable TTL policy. Blocked by OME-778.

Spec: `docs/spec/2026-08-11-OME-777-cacheable-web-search.md`
Plan: `docs/plan/2026-08-11-OME-777-cacheable-web-search.md`
Ledger: `docs/work/2026-08-11-OME-777-cacheable-web-search.md`
