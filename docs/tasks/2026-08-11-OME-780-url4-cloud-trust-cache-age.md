---
id: OME-780
linear_url: https://linear.app/openmined/issue/OME-780/trust-proven-cache-age-and-retire-the-defensive-re-issue
status: Backlog
type: Improvement
priority: P2
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-11
closed:
---

# Trust proven cache age and retire the defensive re-issue

Phase 1b. Parse the Age header from aigateway, send max-age on bounded runs, and stop discarding hits whose freshness is now provable. The defensive re-issue is retained for the version-skew case where no Age header arrives. Blocked by OME-779.

Spec: `docs/spec/2026-08-11-OME-777-cacheable-web-search.md`
Plan: `docs/plan/2026-08-11-OME-777-cacheable-web-search.md`
Ledger: `docs/work/2026-08-11-OME-777-cacheable-web-search.md`
