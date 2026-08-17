---
id: OME-864
linear_url: https://linear.app/openmined/issue/OME-864/add-direct-openai-platform-api-key-provider-to-aigateway
status: Pick Immediately
type: Feature
priority: Urgent
labels: [aigateway, agentic, autonomous]
created: 2026-08-17
closed:
---

# Add direct OpenAI Platform API-key provider to AIGateway

Add API-key-only direct OpenAI access under `openai/*` without changing the existing
`codex/*` OAuth or `openrouter/openai/*` routes.

Canonical artifacts:

- Spec: `docs/spec/2026-08-17-OME-864-direct-openai-provider.md`
- Plan: `docs/plan/2026-08-17-OME-864-direct-openai-provider.md`

Offline source implementation and deterministic verification are complete on the dedicated branch.
Release remains blocked until the approved twelve-model seed and `openai/gpt-5-nano` readiness probe
are verified with an owner-supplied local key and bounded spend. Per owner instruction, Linear
OME-864 remains unchanged for now; the separate OpenAI caching issue will be filed later.
