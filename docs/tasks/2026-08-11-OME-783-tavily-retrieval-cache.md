---
id: OME-783
linear_url: https://linear.app/openmined/issue/OME-783/cache-tavily-retrieval-results
status: Backlog
type: Feature
priority: P2
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-11
closed:
---

# Cache Tavily retrieval results

Phase 4. Add a TTL'd retrieval cache in url4-cloud keyed on the normalized query and exclusion set, wrapping the Tavily calls that never traverse aigateway and therefore cannot benefit from its cache. Independent of OME-781 and OME-782.

Spec: `docs/spec/2026-08-11-OME-777-cacheable-web-search.md`
Plan: `docs/plan/2026-08-11-OME-777-cacheable-web-search.md`
Ledger: `docs/work/2026-08-11-OME-777-cacheable-web-search.md`
