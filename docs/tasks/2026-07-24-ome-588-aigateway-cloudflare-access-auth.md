---
id: OME-588
linear_url: https://linear.app/openmined/issue/OME-588
status: Backlog
type: Epic
priority: P2
labels: [aigateway, autonomous, agentic]
parent: 
created: 2026-07-24
closed:
---

# Cloudflare Access federated authentication for aigateway

Run aigateway behind Cloudflare Access: users admitted by the edge policy get accounts provisioned just-in-time from the verified identity assertion, with no registration and no /v1/auth/login. Programmatic SDK clients authenticate non-interactively while staying individually attributable.

Spec: `docs/spec/2026-07-24-aigateway-cloudflare-access-auth-spec.md`
Plan: `docs/plan/2026-07-24-aigateway-cloudflare-access-auth.md`
