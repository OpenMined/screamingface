---
id: OME-797
linear_url: https://linear.app/openmined/issue/OME-797/unify-url4-cloud-web-search-onto-one-route-flag-with-programmatic
status: In Progress
type: Feature
priority: P2
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-12
closed:
---

# Unify url4-cloud web search onto one route flag with programmatic native/Tavily routing

Replace the per-route `web_tools` / `native_web_search` pair with one `web_search` flag that
defaults to true. The mechanism becomes derived: a route whose provider segment is in
`WEB_SEARCH_NATIVE_PROVIDERS` delegates natively to aigateway, every other route takes the
Tavily tool loop. The set holds only `openrouter`, because that is the one aigateway plugin
declaring a `web_search` parameter. The retired keys raise `WorldConfigError`.

Spec: `docs/spec/2026-08-12-OME-797-unify-web-search.md`
Plan: `docs/plan/2026-08-12-OME-797-unify-web-search.md`
Ledger: `docs/work/2026-08-12-OME-797-unify-web-search.md`
