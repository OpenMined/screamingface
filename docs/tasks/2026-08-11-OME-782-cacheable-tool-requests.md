---
id: OME-782
linear_url: https://linear.app/openmined/issue/OME-782/make-tool-bearing-requests-cacheable
status: Backlog
type: Feature
priority: P2
labels: [aigateway, agentic, autonomous]
created: 2026-08-11
closed:
---

# Make tool-bearing requests cacheable

Phase 3, Path A. Remove the tools and tool_choice presence-bypass and key both fields, leaving metadata's bypass untouched. Widest blast radius in the epic — affects every provider supporting function calling. The tools array is keyed verbatim and deliberately never sorted. Blocked by OME-779.

Spec: `docs/spec/2026-08-11-OME-777-cacheable-web-search.md`
Plan: `docs/plan/2026-08-11-OME-777-cacheable-web-search.md`
Ledger: `docs/work/2026-08-11-OME-777-cacheable-web-search.md`
