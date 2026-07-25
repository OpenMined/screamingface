---
id: OME-589
linear_url: https://linear.app/openmined/issue/OME-589
status: Backlog
type: Refactor
priority: P2
labels: [aigateway, autonomous, agentic]
parent: OME-588
created: 2026-07-24
closed:
---

# Refactor current_account into an ordered IdentityResolver chain

Behavior-preserving: replace the if-tree in current_account with an ordered resolver chain so Cloudflare Access and API-key credentials become additive. Every existing auth test must pass unmodified.

Spec: `docs/spec/2026-07-24-aigateway-cloudflare-access-auth-spec.md`
Plan: `docs/plan/2026-07-24-aigateway-cloudflare-access-auth.md`
