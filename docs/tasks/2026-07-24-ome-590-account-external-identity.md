---
id: OME-590
linear_url: https://linear.app/openmined/issue/OME-590
status: Backlog
type: Feature
priority: P2
labels: [aigateway, autonomous, agentic]
parent: OME-588
created: 2026-07-24
closed:
---

# Add external-identity columns to accounts and make password_hash nullable

accounts gains external_idp + external_subject (unique together) and email; password_hash becomes nullable. INVARIANT: login() explicitly rejects null-hash accounts with the generic 401 — federated accounts cannot password-login.

Spec: `docs/spec/2026-07-24-aigateway-cloudflare-access-auth-spec.md`
Plan: `docs/plan/2026-07-24-aigateway-cloudflare-access-auth.md`
