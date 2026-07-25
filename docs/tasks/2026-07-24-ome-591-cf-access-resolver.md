---
id: OME-591
linear_url: https://linear.app/openmined/issue/OME-591
status: Backlog
type: Feature
priority: P2
labels: [aigateway, autonomous, agentic]
parent: OME-588
created: 2026-07-24
closed:
---

# Add the Cloudflare Access identity resolver with JWKS verification and JIT provisioning

kid-aware JWKS client, RS256 verification of iss/aud/exp, and get_or_create provisioning keyed on (idp, sub) — never email. Reads Cf-Access-Jwt-Assertion, then the CF_Authorization cookie, then Authorization: Bearer.

Spec: `docs/spec/2026-07-24-aigateway-cloudflare-access-auth-spec.md`
Plan: `docs/plan/2026-07-24-aigateway-cloudflare-access-auth.md`
