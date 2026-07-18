---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-18
finished: 2026-07-18
---

# OME-400 — Implement Phase 1 SDK and engine-profile contracts

## Intent

Implement the approved Phase 1 foundation inside the ScreamingFace package stack: immutable
benchmark definitions, engine configuration, remote model/benchmark discovery, strict manifest
and case loading, and a real URL4 profile used for package development. The profile lives
temporarily under `packages/screamingface/apps/sf-url4-engine` until ownership approves promotion
to the repository-level `apps/` directory.

## Planned changes

- Replace the unreleased mock/session/catalog benchmark surface with the approved greenfield
  configuration, public values, strategies, namespaces, registry client, and typed errors.
- Add Phase 1 contract tests before production implementation.
- Add `packages/screamingface/apps/sf-url4-engine` as a tracked Dockerized development profile
  built on `Url4Node`, with registry, manifest, normalized-case, health, and advertised route data.
- Add a prominent README explaining the profile's temporary location and development purpose.
- Align Phase 1 documentation with the temporary tracked location and final registry shape.
- Do not implement Fusion execution, grading execution, aggregation execution, authentication,
  persistence, or direct SDK-to-AI-Gateway behavior.

## Test plan

- Validate `sf.config()` normalization, its localhost default, and lack of network activity.
- Validate immutable `Case`, `Benchmark`, Fusion authoring, and namespaced strategy contracts.
- Validate model and benchmark listing filters against the real registry wire contract.
- Validate eager benchmark manifest/case loading, JSON/NDJSON parsing, and sealed references.
- Cover connection, HTTP, malformed registry, unknown benchmark, invalid manifest/case,
  unsupported tool, and unsupported reducer/schema failures.
- Exercise the actual sf-url4-engine ASGI app over HTTP without invoking model routes or AI
  Gateway.
- Run the complete ScreamingFace format, lint, typecheck, and 95%-coverage gates.

## Acceptance

- Phase 0 fixtures construct using the real public API.
- `sf.models.list()` and `sf.benchmarks.list()` return canonical IDs from the configured engine.
- `sf.benchmarks.load("gpqa@1" | "draco@1")` returns validated immutable definitions and cases.
- The tracked development profile serves the approved plaintext registry, manifests, and NDJSON
  routes through a real `Url4Node`.
- No SDK mock/in-process execution path, static model catalog, or direct gateway client remains
  in the Phase 1 public path.
- No Phase 2 model execution is introduced.

## Outcome

- **Actual files:** replaced the unreleased mock/session execution surface with Phase 1 values,
  namespaces, configuration, discovery/loading, strict wire decoders, and tests under
  `packages/screamingface`; added the temporary `packages/screamingface/apps/sf-url4-engine`
  package, Docker/Compose stack, registry/catalog routes, canonical dataset loaders, README,
  lockfile, and app tests; updated the OME-400 plan/spec/task, CI contract-fixture gate, and
  Docker context exclusions.
- **Commits:** pending owner commit.
- **Gates:** Ruff and formatting green on all owned Phase 1 paths; Pyright green; 66 parent test
  runs green with 97% SDK coverage; 9 isolated app tests green with 100% app coverage; all four
  Phase 0 fixtures construct; SDK wheel and sdist build; Compose validates; the actual engine
  image builds, starts, and serves `/healthz` plus `/.well-known/screamingface`; the SDK lists
  all four advertised models and both benchmarks from that container over real HTTP.
- **Deviations:** per the owner's explicit greenfield decision, superseded unreleased runtime
  tests were replaced instead of preserved, so the repository's generic append-only test check
  is intentionally not applicable to this contract reset. The broad local Ruff command also
  sees the owner's unrelated untracked `packages/screamingface/examples/draco-eval-demo/`
  directory; validation excluded that directory without modifying it. Canonical upstream
  revision pinning remains Phase 4 as planned.
