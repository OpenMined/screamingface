---
title: ScreamingFace Engine provider connections
ticket: OME-766
status: approved
date: 2026-08-06
---

# ScreamingFace Engine provider connections

## Outcome

The ScreamingFace Client can inspect and manage the caller's enabled AI-provider connections
through the Engine without learning AI Gateway account identifiers, credential locators, OAuth
state as a standalone value, or provider response bodies.

The Engine exposes:

- `GET /v1/connections`
- `PUT /v1/connections/{provider}`
- `POST /v1/connections/{provider}/oauth`
- `DELETE /v1/connections/{provider}`

## Ownership

AI Gateway remains authoritative for enabled providers, supported authentication methods, and
stored connection state. The Engine owns a small public projection and forwards only the verified
caller identity installed by the deployment boundary.

Within AI Gateway, `screamingface` is the explicit designation for the row managed by the Engine.
The label is an opt-in inter-service marker, not proof of creator identity: assigning it through
another Gateway surface intentionally opts that row into Engine management. Rows under every other
label are neither projected nor mutated. A missing designated row is `not_connected`, even when
unrelated rows exist for the same provider.

The Client never calls AI Gateway directly. Provider API keys are write-only: the Engine accepts
one long enough to forward it and never returns it.

## Contract

Each public connection contains only:

- provider identifier and display name;
- supported authentication methods;
- public connection status;
- the selected authentication method, when connected; and
- an optional non-secret account label for OAuth connections.

Provider identifiers must be one lowercase URL path segment. Connection identifiers received from
AI Gateway must be UUIDs before they can enter an upstream request path. OAuth authorization URLs
must be HTTPS and their lifetime is bounded to 30 minutes.

API-key connect creates the designated row or replaces its key only when it already uses API-key
authentication. Changing authentication methods never deletes a working connection implicitly:
when the designated row already uses another method, the Engine returns a secret-free 409 and
requires an explicit disconnect first. Disconnect is idempotent, including concurrent retries, and
never deletes a row under another label.

AI Gateway failures are translated to stable, secret-free RFC 9457 problems. Transport timeouts and
unavailability remain distinguishable. Upstream payloads, credentials, and exception text never
become public error details. Request validation at these routes is likewise replaced with a
secret-free problem, because FastAPI's default validation body can include the rejected API-key
input. Successful connection responses use `Cache-Control: private, no-store` and
`Vary: X-User-Email`; this also prevents caching an OAuth URL containing one-time state.

## Composition

When `URL4_CLOUD_AIGATEWAY_BASE_URL` is absent in production, the connection service is disabled
and the routes return 503. Local mode uses the existing loopback AI Gateway at
`http://127.0.0.1:9105` unless explicitly overridden.

## Dependencies and exclusions

The adapter consumes AI Gateway's provider-discovery contract from the separate Gateway PR. This
unit does not change AI Gateway, model-parameter contracts, executable model filtering, benchmark
execution, DRACO, IFEval, deployment charts, or the Client implementation.
