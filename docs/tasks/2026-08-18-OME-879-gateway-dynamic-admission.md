---
id: OME-879
linear_url: https://linear.app/openmined/issue/OME-879/aigateway-post-v1modelsadmit-validate-against-openrouter-catalog
status: in_progress
type: feature
priority: high
labels: [aigateway, agentic, autonomous]
created: 2026-08-18
closed:
---

# aigateway: POST /v1/models/admit — validate against OpenRouter catalog, register dynamically

Gateway half of `OME-878`. New `POST /v1/models/admit` endpoint: flag gate
(`AIGW_OPENROUTER_DYNAMIC`, default true) → id shape → provider enabled → credentialed →
OpenRouter public catalog lookup (OME-479 discovery transport, TTL-cached). Hit → register
the model live + in-memory admitted set, idempotent. Miss → pre-spend refusal with a
diagnostic code (`dynamic_admission_disabled` / `provider_disabled` /
`provider_not_credentialed` / `model_not_on_openrouter`).

Ledger: `docs/work/2026-08-18-OME-879-gateway-dynamic-admission.md`.
