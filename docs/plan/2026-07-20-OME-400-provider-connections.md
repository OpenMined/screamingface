# OME-400 — Provider connections implementation plan

**Status:** Phases 6A–6C complete
**Date:** 2026-07-20
**Normative contract:**
[`docs/spec/2026-07-20-OME-400-provider-connections-contract.md`](../spec/2026-07-20-OME-400-provider-connections-contract.md)

This plan adds provider connections without changing the approved benchmark, URL4 expression, or
dataset boundaries. Each runtime phase still requires the owner's explicit execution approval.

## Phase 6A — SDK connection foundation

**Implementation status:** complete on 2026-07-20.

Add the connection vocabulary and HTTP contract against deterministic fake-engine transports
before changing the development engine.

- extend engine discovery values with providers, authentication methods, and explicit
  model-provider ownership;
- add immutable `Connection` values and the `sf.connections.list()` namespace operation;
- add immutable `OAuthFlow` values whose bounded `wait()` and idempotent `cancel()` remain scoped
  to the engine that created the flow;
- add `sf.connect(...)` and `sf.disconnect(...)` signatures with strict provider/method argument
  validation and no Fusion-owned auth methods;
- add stable connection and secure-transport exception types;
- implement the JSON connection/error decoders without retaining raw secrets or Gateway payloads;
- require HTTPS for non-loopback private operations while preserving the localhost default; and
- add stage-requirement planning for members, model reducers, and model judges without changing
  benchmark loading or model discovery.

Complete when the public surface, immutable values, decoder failures, transport checks, and
stage-requirement sets pass unit and HTTP-contract tests against a fake engine. No widget or real
Gateway connection is required in 6A.

## Phase 6B — screamingface-engine connection bridge

**Implementation status:** complete on 2026-07-20.

Add the protected JSON control plane to the temporary development engine profile.

- extend the canonical engine catalog with public provider definitions and private Gateway
  mappings;
- advertise provider capabilities and explicit model-provider ownership in the public registry;
- intercept `/v1/connections` routes in the application ASGI wrapper before delegating all other
  work to `Url4Node`;
- adapt list/status, OAuth start/completion, API-key create/replace, and idempotent disconnect to
  AI Gateway's existing `default` provider profiles;
- normalize Gateway responses and errors into the approved public schemas;
- relay OAuth callbacks through the engine's provider-specific registered paths and return
  minimal escaped HTML;
- add bounded connection-client lifecycle, timeouts, response limits, and secret-safe logging;
- persist the local Gateway database, encrypted credential blobs, and generated local master key
  on a named Docker volume; and
- keep host publication loopback-only and document that anonymous mode is local-only.

Complete when engine unit tests cover every route/status/error and Docker tests prove restart
persistence, disconnect/reset behavior, engine-only Gateway access, and no credential echo. Do not
modify AI Gateway or URL4.

## Phase 6C — SDK flows, preflight, and widget

**Implementation status:** complete on 2026-07-20.

Wire the approved Python calls to the real engine control plane and add the notebook experience.

- make `sf.connect()` return the all-provider panel and make targeted calls follow the approved
  single-method/multiple-method/idempotency rules;
- implement explicit OAuth and API-key flows plus idempotent `sf.disconnect()`;
- refresh connection reads on every list, action, widget refresh, OAuth poll, and execution
  preflight;
- integrate bounded OAuth polling and cancellation into the widget, including manual refresh and
  non-interactive script output;
- preflight `run`, `grade`, and `evaluate` at their approved stage boundaries and raise one
  structured `ConnectionRequiredError` before model spend;
- preserve completed work and stop unscheduled dependent work when a stored credential is rejected
  during execution;
- render the compact accessible panel using the ScreamingFace design tokens and component rules;
- clear masked key controls after every attempt and keep live connection state out of serialized
  notebooks; and
- update the authentication guide, quickstart prerequisites, architecture guide, README, and API
  reference only after the behavior is implemented.

Complete when the notebook and script paths behave consistently, connection errors are actionable,
the sentinel-secret suite is clean, deterministic notebook regeneration passes, and an opt-in
Docker proof exercises both API-key and OAuth adapters without a paid model call.

## Explicitly deferred

- hosted ScreamingFace login and identity-token acquisition;
- multiple named profiles per provider;
- copying connections between engines;
- dataset credential management;
- validating a key through a hidden model call;
- connection-dependent model discovery;
- provider usage, price, budget, or entitlement probing; and
- any AI Gateway or URL4 source change.

## Verification matrix

| Boundary | Required proof |
|---|---|
| Public registry | provider capabilities are public; private Gateway aliases are absent |
| Connection status | sanitized engine-local records on loopback; hosted exposure requires authenticated user scoping |
| API key | PUT body only; never echoed, redirected, logged, serialized, or retained |
| OAuth | engine callback, single-use state, bounded polling, cancellation and expiry |
| Benchmark | dataset loading works independently of provider connections |
| Run | member and model-reducer requirements checked once before model calls |
| Grade | model judge checked only when grading needs it |
| Evaluate | complete requirement union checked before model spend |
| Discovery | supported models remain visible while disconnected |
| Docker | local credentials persist across restart; explicit volume reset removes them |
| Widget | compact, square, keyboard-accessible, light/dark-safe, no serialized private state |
| Hosted boundary | non-loopback private traffic requires HTTPS; anonymous deployment unsupported |
