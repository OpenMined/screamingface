---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-18
finished: 2026-07-18
---

# OME-400 — Implement Phase 2A persistent engine model routes

## Intent

Implement the approved first Phase 2 vertical slice without adding reducer execution or SDK
orchestration. `screamingface-engine` must remain one persistent, framework-free `Url4Node`
application whose in-process model handlers exclusively contact AI Gateway.

## Changes

- Add one canonical public-model/private-Gateway catalog and derive discovery from it.
- Register three verified tool-free model handlers on the persistent node.
- Translate resolved URL4 context, intent, and allowlisted typed parameters to AI Gateway chat.
- Reuse one asynchronous Gateway client and return only validated assistant plaintext.
- Add an application-owned ASGI lifecycle/admission/timeout wrapper around `node.asgi()`.
- Move benchmark resources to their approved unprefixed routes.
- Wire the local Compose engine to the AI Gateway service.
- Document that `web_search` and the unverified DRACO judge route are not currently advertised.

## Test plan

- Cover public/private model mapping, parameter validation, shared client reuse, and Gateway
  transport/status/schema failures.
- Exercise direct model dispatch and a complete `GET /v1?q=...` URL4 expression.
- Cover 503 admission, 504 whole-evaluation timeout, startup, and graceful shutdown.
- Run app and SDK formatting, lint, type, test, coverage, lockfile, and Compose validation gates.

## Outcome

- **Actual files:** added engine settings, AI Gateway adapter, and ASGI lifecycle modules; revised
  node composition, catalog, CLI, Compose, runtime dependencies, app/SDK documentation, plan,
  contract, task ledger, and Phase 1 walkthrough copy; added focused settings, Gateway, ASGI,
  catalog, and HTTP tests.
- **Commits:** none; the user owns commit and push.
- **Gates:** 33 engine tests pass at 98% coverage; 57 SDK tests pass at 97% coverage; Ruff lint and
  formatting, Pyright, lockfile validation, Compose validation, Phase 1 fixture construction,
  package build, Docker engine-image build, and `git diff --check` pass.
- **Container smoke:** the built image starts as the persistent application and serves the
  expected health and tool-free discovery documents over real HTTP; no provider call was made.
- **Deviations:** named tools, the unavailable DRACO judge model, the deterministic reducer,
  Docker end-to-end proof, and SDK orchestration remain in their approved later slices.
