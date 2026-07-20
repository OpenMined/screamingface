---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — derive engine model routes from AI Gateway discovery

## Intent

Remove the duplicated ScreamingFace model-availability list. The engine will discover the
AI Gateway catalog once during startup, expose every model belonging to a ScreamingFace-supported
provider, and build URL4 routes plus `/.well-known/screamingface` from the same resolved records.
ScreamingFace continues to own public aliases, provider auth metadata, named-tool claims, and
deployment exposure policy; the SDK continues to contact only the ScreamingFace engine.

## Planned changes

- Replace static availability in `screamingface_engine.catalog` with strict Gateway catalog
  decoding and deterministic public-route normalization.
- Add `GatewayClient.list_models()` over `GET /v1/models`.
- Initialize the application-owned `Url4Node` from the resolved catalog before startup completes.
- Keep direct `EngineASGI(node, ...)` construction for isolated generic wrapper tests only; the
  production `create_app()` path has no static or stale model fallback.
- Update engine/SDK contract tests, docs, and live registry verification.

## Test plan

- RED: catalog records forward every known supported-provider model in Gateway order.
- RED: provider-qualified request IDs and public aliases are derived exactly for Anthropic,
  Codex, and Gemini.
- RED: unknown providers are omitted; malformed/duplicate/empty supported catalogs fail startup.
- RED: engine registry and registered URL4 routes use the same resolved tuple.
- RED: Gateway connection/status failures prevent engine readiness with a safe startup failure.
- RED: SDK discovery and execution still target only the configured engine origin.

## Acceptance

- Adding a model to an already supported AI Gateway provider requires no ScreamingFace availability
  edit and appears after engine restart.
- Removing a Gateway model removes its engine route after restart.
- Public aliases and named tools remain explicit ScreamingFace policy.
- No catalog request occurs per SDK discovery or model execution request.
- Full ScreamingFace gates, notebook determinism, skill validation, Docker health, and live
  Gateway/engine catalog comparison pass.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** engine catalog, Gateway adapter, application composition/lifecycle, engine
  tests and test-only model fixtures; public architecture/spec/task docs and engine README.
- **Commits:** `feat(screamingface-engine): derive model routes from gateway` (this commit)
- **Gates:** authoritative `screamingface` gate green: Ruff, format, Pyright, SDK and engine
  coverage, Phase 1 fixtures, deterministic notebooks, and wheel build. Engine unit suite: 151
  passed. Live Compose health, raw Gateway catalog, engine registry, and `sf.models.list()` were
  compared without provider spend; the 20 raw Gateway records produced the expected 14 public
  routes for supported providers.
- **Deviations:** the append-only guard was explicitly waived for the approved migration from the
  removed production `MODEL_ROUTES` constant to a test-only injected catalog fixture. Existing
  tests were preserved semantically and the full suite remained green. `antigravity` and
  `huggingface` records are intentionally omitted until ScreamingFace defines their provider and
  connection contracts. No SDK transport, AI Gateway source, or generic URL4 source changed.
