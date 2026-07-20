---
ticket: OME-428
stack: aigateway
status: done
started: 2026-07-17
finished: 2026-07-20
---

# OME-428 - Checkpoint A: BYOK OpenRouter provider

## Intent

Ship an independently releasable OpenRouter provider using account-scoped encrypted API keys and
the existing AIGateway provider interfaces. Keep hosted credentials, deployment policy, and other
providers outside this checkpoint.

## Delivered

- Added a disabled-by-default `openrouter` provider with environment-backed settings, registry
  discovery, account-scoped `ApiKeyStrategy`, and seed model registration.
- Kept upstream model IDs in the form `openrouter/<author>/<model>` and pinned dispatch to
  `https://openrouter.ai/api/v1` after ingress has removed caller routing overrides.
- Rejected streaming before credential access; Checkpoint A supports non-streaming chat only.
- Added gateway-owned OpenRouter attribution headers while stripping caller attempts to override
  authorization, host, or attribution values.
- Split chat credential and dispatch responsibilities into cohesive route modules; every touched
  Python source file remains below 450 lines.
- Preserved native usage, cost details, generation identifiers, and BYOK metadata in successful
  responses.

## Security And Error Contracts

- The gateway owns credentials and upstream routing. Shared ingress strips LiteLLM control-plane
  fields for credentials, bases, fallbacks, retries, callbacks, logging, telemetry credentials and
  hosts, and message-redaction controls. Nested metadata is copied before unsafe keys are removed,
  so caller input is not mutated and unrelated provider metadata survives.
- Local API keys remain in the existing encrypted credential store. No plaintext credential is
  logged, returned, placed in a cache key, or persisted as provider error detail.
- Provider error responses use gateway-authored messages. Raw exception text, provider metadata,
  prompts, and secrets are not serialized or logged by the route error boundary.
- Only an `httpx.HTTPError` cause proves a transport failure. The pinned LiteLLM converter shape
  identifies an already-returned HTTP-200 body error; all other shapes are ambiguous. Body and
  ambiguous errors are non-retryable to avoid duplicate billable dispatches.
- Known LiteLLM HTTP exceptions preserve validated 4xx/5xx status codes. Unknown exceptions and
  hostile exception properties fail closed to a sanitized 502. Secondary failures while updating
  credential state are also contained as sanitized 502 responses.
- Only a proven 401 marks the selected account connection errored. 402, 403, 408, 429, and 5xx
  responses do not invalidate a usable key.
- Retryable transport statuses are 429, 503, and 529. `Retry-After` source precedence is
  `response.headers`, `litellm_response_headers`, then exception headers. The accepted form is one
  or more unsigned ASCII digits; invalid earlier sources do not hide a valid later source. Values
  beyond the supported integer range remain budget-exceeding instead of falling back to another
  dispatch.

## Architecture

- Shared request hardening, HTTP-status validation, retry policy, and provider-error markers live
  in `aigateway.core`.
- OpenRouter model validation, attribution, embedded-error handling, and LiteLLM provenance remain
  provider-local.
- The existing credential strategy, OAuth connection store, request cache, and provider registry
  interfaces remain unchanged.
- No ORM model, schema, migration, dependency, lockfile, hosted mode, billing, or cache contract
  changed in this checkpoint.

## Verification

- Focused security and error regression suite: `131 passed`.
- Full non-live AIGateway suite: `1020 passed, 29 skipped`, without warnings.
- Append-only test check against `main`, lint, formatting, type checking, no-enterprise import
  guard, and full pytest coverage threshold: all passed.
- Real LiteLLM conversion and callback behavior is exercised with mocked HTTP transport. Tests pin
  converter-vs-transport provenance, single-dispatch body errors, bounded overload retries,
  callback-state isolation, sanitized failures, and selected-connection invalidation.

## Residual And Out Of Scope

- Live OpenRouter smoke testing was not run because it requires owner approval and a real API key.
  It remains required before broad BYOK release.
- Operator-enabled LiteLLM DEBUG logging can include raw request or response data. Callers cannot
  enable it through the chat body; deployments handling sensitive prompts must keep it disabled.
- Hosted shared credentials and deployment admission policy are Checkpoint B. Hugging Face support
  is tracked separately by OME-394.
