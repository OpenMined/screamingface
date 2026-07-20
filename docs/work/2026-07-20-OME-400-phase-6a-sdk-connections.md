---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 6A SDK connection foundation

## Intent

Implement the approved SDK-only provider connection foundation against deterministic fake-engine
transports. Add public provider/connection values, strict HTTP contract parsing, secure transport
validation, and model-stage requirement planning without adding real engine control routes,
Gateway mutations, execution preflight, or notebook widgets.

## Planned changes

- Extend ScreamingFace registry parsing with public providers, authentication methods, and explicit
  model-provider ownership.
- Add immutable public `Connection` values and the `sf.connections.list()` operation.
- Add the approved immutable public `OAuthFlow` with originating-engine-scoped bounded `wait()` and
  idempotent `cancel()` behavior.
- Add the approved `sf.connect(...)` and `sf.disconnect(...)` argument surface backed by the
  configured engine contract, with no Fusion-owned authentication methods.
- Add stable connection, connection-required, and secure-transport errors.
- Add strict JSON connection/error decoding that never retains secrets or private Gateway fields.
- Require HTTPS for non-loopback private connection operations.
- Add internal stage-requirement planning for Fusion members, model reducers, and model judges
  without changing benchmark loading or model discovery.
- Add append-only Phase 6A SDK tests and reconcile the OME-400 plan/task records after gates pass.

## Test plan

- Add a new Phase 6A test module before production changes and confirm RED for the missing public
  surface and registry fields.
- Cover public provider/model parsing, exact field rejection, duplicate identities, unknown
  provider references, and connection-independent model listing.
- Cover immutable connection values, all five statuses, sanitized representations, and strict
  connection/error response parsing.
- Cover no-provider, one-method, multi-method, explicit OAuth, API-key replacement, idempotent
  disconnect, and invalid argument combinations through a fake HTTP engine.
- Prove API keys appear only in the PUT JSON body and never in URLs, errors, representations, or
  captured logs; prove redirects are not followed.
- Cover loopback HTTP acceptance and non-loopback HTTP rejection before any private request.
- Cover member, model-reducer, and rubric-judge requirement sets plus deterministic strategies that
  add no model requirement.
- Run focused RED/GREEN tests, the complete SDK suite, coverage, Ruff, formatting, Pyright, and the
  repository ScreamingFace gate.

## Acceptance

- The exact approved Phase 6A public surface exists and is typed without a widget implementation.
- Public discovery provides provider capabilities and explicit model-provider ownership without
  leaking private Gateway aliases.
- Connection responses are immutable, sanitized, strict, and refreshed on every list/action call.
- Private operations reject insecure non-loopback origins before transmitting data.
- Benchmark loading and model discovery remain connection-independent.
- Requirement planning distinguishes run, grade, and evaluate model roles without performing a
  connection preflight yet.
- No runtime mock, real engine route, AI Gateway change, URL4 change, Fusion auth method, or dataset
  credential manager is introduced.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** updated the provider connection plan/spec/task; added
  `screamingface.connections` and the pure `_requirements` planner; extended `_profile`, public
  exports, and typed errors; added the Phase 6A contract suite; and replaced the owner-approved
  Phase 1 registry fixture with the new strict provider-aware shape.
- **Commits:** `feat(screamingface): add provider connection foundation` (`Refs OME-400`).
- **Gates:** `uv run .claude/scripts/run_gates.py screamingface --skip-append-only` passed all
  Ruff lint, Ruff formatting, Pyright, pytest, and 95% coverage gates; direct full-suite proof was
  431 passed. The skip covered only the explicitly approved prior registry-fixture replacement.
- **Deviations:** `sf.connect()` returns the fresh connection tuple until the approved Phase 6C
  widget exists. No real connection route, Gateway adapter, preflight, widget, dataset credential,
  runtime mock, URL4 change, or AI Gateway change was added.
