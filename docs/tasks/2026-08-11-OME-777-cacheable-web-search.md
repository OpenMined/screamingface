---
id: OME-777
linear_url: https://linear.app/openmined/issue/OME-777/make-web-search-backed-requests-cacheable
status: Backlog
type: Epic
priority: P1
labels: [aigateway, agentic, autonomous]
created: 2026-08-11
closed:
---

# Make web-search-backed requests cacheable

Epic. Make both web-search mechanisms eligible for aigateway's shared global cache without ever serving a caller an answer to a question they did not ask. Two owner decisions (2026-08-11) unblock it: tool-bearing requests may be cached, and the deployment env var AIGW_OPENROUTER_WEB_SEARCH_EXCLUDED_DOMAINS is deleted so the request body becomes the single source of truth for blocked domains. Sub-issues: OME-778, OME-779, OME-780, OME-781, OME-782, OME-783.

Spec: `docs/spec/2026-08-11-OME-777-cacheable-web-search.md`
Plan: `docs/plan/2026-08-11-OME-777-cacheable-web-search.md`
Ledger: `docs/work/2026-08-11-OME-777-cacheable-web-search.md`
