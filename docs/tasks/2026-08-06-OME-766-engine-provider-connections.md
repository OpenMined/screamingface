---
id: OME-766
linear_url: https://linear.app/openmined/issue/OME-766/expose-provider-connection-management-through-the-screamingface-engine
status: Pick Immediately
type: Feature
priority: P1
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-06
closed:
---

# Expose provider connection management through the ScreamingFace Engine

Publish one Engine-owned connection surface for listing caller-scoped provider state, connecting
or replacing an API key, starting provider OAuth, and disconnecting. AI Gateway remains
authoritative for provider capabilities and credential storage; the Engine exposes only validated,
secret-free public values and forwards only the identity already verified by the deployment edge.

Dependencies: OME-497 provides AI Gateway provider discovery; this implementation also satisfies
OME-498's narrower Engine discovery requirement and unblocks the Client work in OME-496.

Spec: `docs/spec/2026-08-06-OME-766-engine-provider-connections.md`
Plan: `docs/plan/2026-08-06-OME-766-engine-provider-connections.md`
Ledger: `docs/work/2026-08-06-OME-766-engine-provider-connections.md`
