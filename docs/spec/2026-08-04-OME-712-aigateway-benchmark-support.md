---
title: OME-712 — AI Gateway support for Engine-owned benchmarks
status: accepted
created: 2026-08-04
ticket: OME-712
related:
  - https://linear.app/openmined/issue/OME-712/run-draco-end-to-end-as-a-url4-expression-on-the-runner-path
  - docs/plan/2026-08-04-OME-712-aigateway-benchmark-support.md
  - docs/work/2026-08-04-OME-712-aigateway-benchmark-support.md
---

# AI Gateway support for Engine-owned benchmarks

## Purpose

Engine benchmark runs use the same AI Gateway contract as every other completion. The Gateway
must register the exact models a deployed Engine may call, expose model/provider discovery,
translate a small provider-neutral web-search request into OpenRouter's private envelope, and
bootstrap its schema predictably in local and container environments.

Benchmark protocols, model composition, grading, and aggregation remain Engine concerns.

## Contracts

### Exact model registration

`OpenRouterPluginSettings.default_models` is the canonical discovery seed set, not an
authorization boundary. Each benchmark model used by this stack must be present so the Engine's
catalog can plan its exact route; a missing seed fails Engine planning rather than being routed
heuristically. Direct Gateway callers may still address any syntactically valid OpenRouter model
id, preserving the provider's BYOK surface. Local launch tooling enables OpenRouter but must not
shadow the plugin-owned canonical list with a second environment override.

### Provider-neutral web search

Callers request hosted retrieval with these standard parameters:

- `web_search: boolean`
- `web_search_excluded_domains: string[]`

Only `web_search: true` enables retrieval; exclusions without it fail closed. The OpenRouter
adapter removes both standard fields from the upstream request and emits its `plugins` envelope.
Operator-configured and caller-supplied excluded domains are unioned, deduplicated, and sent with
OpenRouter's documented `exclude_domains` key. Callers cannot submit an arbitrary OpenRouter
plugin envelope.

OpenRouter's native engines do not all enforce domain exclusions. The Gateway guarantees the
validated request and policy union, not an upstream capability that is model-specific. A
benchmark requiring hard exclusion must select a compatible Engine route; this is checked in the
URL4 Cloud layer.

Providers that do not declare these standard parameters continue to reject them through the
normal parameter contract; the Gateway does not silently ignore unsupported retrieval.

### Discovery

The provider discovery route is available in authenticated and explicitly auth-disabled local
deployments. It reports the plugin-owned provider/model surface consumed by URL4 Cloud and does
not contain benchmark-specific records.

### Schema bootstrap

`aigateway migrate` is the single CLI entry point for applying database migrations before the
service starts. The local launcher and Helm migration Job call that entry point. Plain Docker
exposes it through the image entry point and documents the explicit migrate-then-serve sequence;
the service command does not race migrations across replicas.

## Ownership boundaries

- `aigateway.core.standard_parameters` owns the public parameter names and schemas.
- The OpenRouter plugin owns translation, provider policy, and canonical model seeds.
- Gateway routes own provider/model discovery.
- URL4 Cloud owns benchmark manifests, Candidate invocation, and result interpretation.
- The ScreamingFace SDK never emits OpenRouter's private `plugins` field.

## Failure behavior

- An Engine plan cannot select a model absent from the discovered catalog. Direct Gateway model
  ids remain exact: there is no alias, fallback model, or fuzzy routing.
- Invalid standard parameter values fail validation before provider dispatch.
- Unsupported provider parameters fail closed.
- An invalid migration or database configuration exits non-zero before service startup.

## Non-goals

- Benchmark manifests or benchmark-specific request schemas.
- A general plugin DSL exposed to callers.
- Provider-side web crawling implemented by the Gateway.
- Model aliases or compatibility fallbacks.

## Acceptance

- Canonical settings contain the exact DRACO and current IFEval model ids used by the Engine.
- Local launch migrates before serving and preserves that canonical model list.
- OpenRouter receives the correct web plugin envelope and `exclude_domains` spelling.
- Caller/operator exclusion policy composes deterministically.
- Discovery and migration behavior are covered at application seams.
- The complete AI Gateway gate passes without weakening inherited tests.
