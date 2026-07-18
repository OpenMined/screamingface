---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-18
finished: 2026-07-18
---

# OME-400 — Revise the Phase 2 persistent-engine contract

## Intent

Revise the approved Phase 2 plan and normative benchmark contract around the actual public
`Url4Node` server API. `screamingface-engine` is one persistent Python/ASGI service with
startup-registered, in-process model and reducer handlers. It is not a TOML `[commands]` profile
that launches the engine executable again for every URL4 node.

## Planned changes

- Make the persistent `Url4Node` process and in-process endpoint lifecycle explicit.
- Remove the redundant `/sf` prefix from ScreamingFace-owned model-adjacent resource routes.
- Define one canonical engine catalog as the source of route registration, public discovery, and
  private AI Gateway model mappings.
- Lock the URL4 `Request` to AI Gateway request translation, parameter validation, plaintext
  response extraction, and transient failure boundary.
- Lock a thin application-owned ASGI lifecycle/admission wrapper around `node.asgi()` without a
  second routing framework or a private URL4 import.
- Lock atomic per-case execution, stable incomplete runs, typed failure categories, and no
  automatic paid-call retries.
- Separate core `Url4Node` protocol features from the optional `url4 serve` TOML/command wrapper.
- Tighten the Phase 2 SDK, engine, Docker, and HTTP completion gates without changing runtime code.

## Test plan

- Search the normative plan/spec for stale `/sf` reducer or benchmark routes.
- Search Phase 2 text for any claim that the engine executable is a per-request command.
- Verify all expression, registry, manifest, and architecture examples use the same route names.
- Run `git diff --check`; no runtime, test, application, or notebook files change in this unit.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** revised the Phase 2 architecture plan and normative benchmark contract; added
  this work record. No runtime, tests, application code, or notebooks changed in this planning
  unit.
- **Commits:** none created; the user owns commit and push.
- **Gates:** normative route audit has no stale `/sf` benchmark/reducer paths; the concrete Fusion
  expression parses and render/build round-trips with the current URL4 package; `git diff --check`
  passes.
- **Deviations:** the already-implemented Phase 1 app still exposes its provisional namespaced
  resource paths. The approved Phase 2 implementation replaces them without compatibility aliases.
