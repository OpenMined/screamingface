---
name: url4-engine
description: Implement or review URL4 execution, Url4Node registries, raw-ASGI serving, the url4 serve/eval CLI, or an application-owned URL4 node profile. Use this skill to distinguish implemented GET-only engine contracts from proposed streaming, telemetry, and Enclave architecture.
---

# URL4 engine

Announce that this skill is being used and whether the work targets generic `packages/url4` or an
application-owned node profile.

## Implemented today

`packages/url4` provides:

- grammar/parser and Python builders for URL4 expressions;
- DAG nodes and execution over an `IOLayer`;
- `Url4Node`, itself an `IOLayer`, with endpoint, data, holding, and identity registries;
- one shared dispatch path for in-process evaluation, nested subrequests, and HTTP requests;
- framework-free raw ASGI serving with transactional `GET /v1?q=<expression>`;
- `url4 eval` for network-free one-shot evaluation; and
- `url4 serve` with optional, lazily imported uvicorn support and `url4.toml` registries for
  commands, data, holdings, and identities.

Successful URL4 results are plaintext unless the evaluated expression itself constructs structured
text. Parse errors and execution failures map to HTTP errors. The generic server has no built-in
authentication, so it binds to loopback by default; exposing it requires an application security
boundary. Command routes execute subprocesses and are disabled unless explicitly configured.

## Generic versus application-owned behavior

Generic syntax, parsing, DAG execution, I/O semantics, and node dispatch belong in `packages/url4`.
Provider routing, credentials, model catalogs, benchmark policy, and deployment-specific limits do
not.

The temporary `packages/screamingface/apps/screamingface-engine` profile is one persistent
`Url4Node` application with Python-registered handlers. It owns:

- the ScreamingFace capability registry;
- public model/reducer routes;
- the private provider-connection control plane;
- AI Gateway model adapters and the engine-owned Tavily tool service;
- request admission, timeouts, and encoded request-target limits.

The ScreamingFace SDK calls only this engine. Only engine model handlers contact AI Gateway.
Registry entries must describe capabilities that the running deployment can actually execute.

Do not force this profile into `url4.toml`: Python handlers are appropriate when a route needs
shared async clients, lifecycle, auth state, validation, or multi-step tool execution. TOML is the
right fit for declarative command/data/holding/identity registration in the generic CLI.

## Core invariants

- The URL4 expression is the transactional address; HTTP evaluation remains GET-only.
- `Url4Node` is the single registry-backed dispatch authority. Do not create a parallel router with
  divergent semantics.
- Core URL4 imports remain framework-free; uvicorn is optional and lazy.
- Backend adapters register at the application boundary; generic URL4 code does not import model
  providers or AI Gateway.
- Nested references are resolved by the DAG/I/O layer. Do not pre-populate values in the client as
  though the engine were merely receiving a completed response.
- Use bounded concurrency, timeouts, and safe errors at the owning application boundary.
- Do not advertise authentication, streaming, telemetry, usage, cost, or tool support that is not
  implemented end to end.

## Proposed, not implemented

The diagrams under `docs/diagrams/ensemble-node-*` explore a future architecture with WebSocket
streaming, W3C trace propagation, OTel GenAI spans, separate `cost.usage` events, per-hop telemetry
relay, an Enclave trace store, and RFC 8288 result links. These are design inputs only. They are not
current `Url4Node`, `url4 serve`, or ScreamingFace-engine contracts.

Before implementing any of them, require an approved spec that resolves transport negotiation,
event envelopes, persistence ownership, authentication, backpressure, and the open question of how
transactional leaf telemetry is returned. Never infer these features from the existing diagrams.

## Validation routing

- Generic URL4 change: run the `url4` stack from `.claude/sdlc.local.md`.
- ScreamingFace profile change: run the complete `screamingface` stack, including engine coverage
  and deterministic notebook/fixture checks.
- Cross-boundary contract change: use separate work items per affected package/app and test both
  sides against the same fixture.
