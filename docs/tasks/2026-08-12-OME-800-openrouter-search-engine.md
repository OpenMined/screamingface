---
id: OME-800
linear_url: https://linear.app/openmined/issue/OME-800/stop-forcing-the-openrouter-web-search-engine
status: In Progress
type: Feature
priority: P2
labels: [aigateway, agentic, autonomous]
parent: OME-799
created: 2026-08-12
closed:
---

# Stop forcing the OpenRouter web-search engine

Drop the hardcoded `engine: "native"` from OpenRouter's web-plugin envelope so OpenRouter
selects native-or-Exa itself, and bump the cache adapter revision `08c` → `08d`. This makes
"OpenRouter searches natively" true for the whole provider, which is what lets OME-797 route
by provider instead of by model.

Ledger: `docs/work/2026-08-12-OME-800-openrouter-search-engine.md`
Epic: OME-799 · Sibling: OME-797
