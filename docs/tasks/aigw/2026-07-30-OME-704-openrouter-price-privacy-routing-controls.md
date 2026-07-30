---
id: OME-704
linear_url: https://linear.app/openmined/issue/OME-704/expose-validated-openrouter-price-and-privacy-routing-controls-per
status: in_progress
type: Feature
priority: High
labels: [aigateway, agentic, autonomous]
created: 2026-07-30
closed:
---

# OME-704 — Expose validated OpenRouter price and privacy routing controls per request

Parent: OME-479 (expose provider API parameters). Related: OME-702 (cache fingerprint),
OME-703 (provider/endpoint pinning — deferred), OME-309 (catalog pricing metadata).

## Scope

Five caller-visible leaves under the existing `provider_params` wrapper, expressing four
logical OpenRouter controls:

```text
provider_params.sort                   -> provider.sort              (enum: price)
provider_params.max_price_prompt       -> provider.max_price.prompt   (decimal string)
provider_params.max_price_completion   -> provider.max_price.completion
provider_params.data_collection        -> provider.data_collection    (enum: allow | deny)
provider_params.zdr                    -> provider.zdr                (boolean; false omitted)
```

AIGateway validates each leaf and reconstructs the upstream `provider` object from an
explicit allowlist, always forcing `require_parameters=true`. Raw `provider`, `order`,
`only`, `ignore`, `allow_fallbacks`, `route`, `models` and `plugins` remain named
unknown-parameter rejections. Every new rule declares `cache_behavior="bypass"` until
OME-702 can key the complete resolved routing policy.

`max_price` is a unit-rate ceiling (USD per million tokens), not a request or run budget.
`data_collection="deny"` filters OpenRouter's data-collection/training classification and is
not a retention guarantee. `zdr=true` is upstream endpoint eligibility only — it makes no
claim about retention by AIGateway, URL4, logs, tools or caches.

## Out of scope

Provider/endpoint pinning, provider ordering beyond `sort="price"`, model fallbacks, profile
or deployment defaults, URL4 transport, total-spend budgets, cache redesign, client UI,
catalog pricing acquisition, and OpenRouter `reasoning_effort`.

## Artifacts

- Task definition + implementation plan:
  `.agent-team-AIGW/expose-validated-openrouter-price-and-privacy-routing-controls-per-request/`
- Work ledger: `docs/work/aigw/2026-07-30-OME-704-openrouter-price-privacy-routing-controls.md`

## Status

In progress. Definition of done tracked on the Linear issue (13 items).
