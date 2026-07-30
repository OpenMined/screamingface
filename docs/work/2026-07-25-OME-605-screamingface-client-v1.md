---
ticket: OME-605
stack: screamingface
status: in_progress
started: 2026-07-25
finished:
---

# OME-605 — Implement the ScreamingFace Python Client v1

## Intent

Replace the exploratory and temporary SDK interfaces with one coherent greenfield v1 contract.
Researchers plan a complete benchmark Evaluation, inspect its canonical URL4, and run it through
the configured SF Engine. The package hides transport and execution-stage complexity behind the
same small synchronous or asynchronous Client interface and assembles one validated Report from
the Engine's Benchmark result and lifecycle Events.

## Planned changes

- Consolidate the approved terminology in `CONTEXT.md`.
- Write one normative v1 contract under `docs/spec/`.
- Write the implementation sequence under
  `docs/plan/2026-07-25-OME-605-screamingface-client-v1.md` after the specification is approved.
- Replace the exploratory ADR set only after its decisions are represented in the approved spec.
- After explicit implementation approval, refactor `packages/screamingface` test-first and update
  its quickstart and package documentation.

## Approved migration exception

On 2026-07-25 the user approved an atomic migration of the unreleased package with no legacy
aliases, deprecation layer, or fallback behavior. The connected compiler, planning, execution,
Report, public-export, test, and notebook surfaces may therefore be temporarily red between
implementation slices. No commit may be created until the complete replacement interface and
retained invariants pass the package gates.

Examples of deliberately unsupported compatibility shims include:

- `reducers.Model = reducers.Synthesis`;
- retaining `Benchmark.evaluate(...)` beside `plan(...)` and `run(...)`;
- retaining Recipe `.url4` beside executable Plan and Report URL4 artifacts; and
- accepting `first`, `params`, or mutable global `sf.config` under their former meanings.

## Test plan

- Design phase: cross-check every public symbol and invariant against the current source,
  URL4-cloud lifecycle contract, and approved examples.
- Implementation phase: add failing interface, validation, serialization, sync/async parity,
  event-handling, transport, rich-display, and end-to-end contract tests before production changes.
- Run the complete `screamingface` stack gates after every implementation unit.

## Progress

- Immutable `Model`, `Fusion`, and `reducers.Synthesis` values implemented with no compatibility
  aliases.
- Keyword-only, network-lazy `Client` and `AsyncClient` configuration implemented.
- Immutable Plan values and the stable `plan(...)` call shape are implemented. The
  speculative resolved-manifest hook and opaque Candidate-spec compiler were removed; planning
  raises a typed blocker until the Engine publishes its manifest, capability-profile, and
  per-Candidate URL4 compilation contracts.
- Unified immutable Event and Report values implemented, including ordered/name Candidate lookup,
  `.only`, flattened typed failures, decimal usage, and JSON serialization.
- Report validation permits a Benchmark to score a Fusion synthesized from partial panel evidence
  while retaining each failed direct member and keeping `report.ok` false. Candidate-owned
  failures still cannot accompany a fabricated score.
- Corrected execution granularity to one complete flat-root URL4 and one Engine Run per Candidate.
  Plans and Reports no longer expose fictitious shared URL4 or Run identities; Candidate Results
  own lifecycle provenance, while Report timing and usage are derived from those independent Runs.
- Public value invariants now reject malformed Benchmark metadata, Plans, Candidate projections,
  Event attributes, model-route summaries, HTTP diagnostics, and inconsistent case selection at
  construction time.
- Model, Synthesis, Fusion, Plan, Candidate collections, and Report values have compact,
  researcher-facing representations. Every planned Candidate renders the actual Engine-inspected
  Operation DAG for its independent URL4.
- REST/WebSocket execution lifecycle implemented against the published URL4-cloud contract:
  capability minting, initial attach, WebSocket negotiation, asynchronous start, ordered
  CloudEvents, replay, best-effort cancellation, generic root result/termination, and
  synchronous/asynchronous callback parity.
- The speculative Candidate-result decoder was removed. `run(...)` fails closed before starting
  paid work until the Engine publishes compatibility-preflight and final Candidate-result
  contracts. The confirmed transport lifecycle remains independently contract-tested.
- Lazy module-level `sf.plan` and `sf.run` implemented over one default Client.
- Built-in terminal/notebook progress is composed from the same ordered typed Event stream as the
  user callback; `progress=` is not a separate or synthetic execution path.
- Simplified the final public vocabulary to `Plan`, `Candidate`, `Operation`, `CandidateResult`,
  and `MemberResult`, with no aliases for the superseded pre-release names. Each Candidate now
  retains the immutable, Engine-inspected Operation DAG for its independently executable URL4.
- The legacy Client API, SSE path, Benchmark authoring surface, connection/tool surface, old
  reducers, obsolete contract fixtures, builders, and notebooks were removed atomically.
- README and three deterministic v1 notebooks teach the target `plan → run` flow while stating
  exactly which production contracts remain gated.
- Full package result: 187 tests pass and 15 contract/integration requirements are skipped, with
  at least 95% coverage; Ruff, format, Pyright, deterministic notebook verification, and wheel
  and sdist content verification all pass.

## Active external and dependency gates

- The production capability-profile, Benchmark-manifest, per-Candidate URL4 compilation, Candidate
  scheduling/cache-reuse, and final Candidate-result contracts are not yet published. The Client
  exposes typed blockers rather than fixture-backed production behavior.
- The user separately approved `websockets>=16.1,<17`; the dependency is implemented and locked.
- Capability refresh for an already running disconnected Run, hosted caller authentication, and
  the authoritative heartbeat/liveness rule remain external SF Engine contract gates.
- OME-587 now provides the real URL4 executor through both an in-process local runner and the
  hosted runner adapter. The opt-in integration test accepts either runner-backed target; the
  ScreamingFace-specific planning and Candidate-result contracts remain separate gates.

## Acceptance

- One approved specification defines the complete public v1 interface and JSON Report contract.
- One approved plan maps the current package to the target interface without compatibility aliases.
- The final implementation satisfies the Linear acceptance criteria and all package gates.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** v1 Client/Recipe/planning/Event/Report/transport modules, replacement tests,
  README, three deterministic notebooks and one builder, package dependency metadata, and OME-605
  contract/plan/task/work artifacts. Obsolete unreleased Client modules and examples were removed.
- **Commits:** `8451da41 feat(screamingface): establish v1 plan and run client contract`
- **Gates:** `uv run .claude/scripts/run_gates.py screamingface --skip-append-only` — all green;
  append-only was skipped under the approved atomic migration exception. Pytest: 187 passed and
  15 skipped external contract/conformance requirements.
- **Review closure:** Plan/Candidate notebook inspection now renders the comparison overview and
  each Engine-inspected Operation DAG. Engine-resolved Plan, Candidate, and Operation values no
  longer have public construction paths. Private named collections share one implementation;
  Report primitives were split from the public Report module to keep both modules within the
  repository size limit. Production and test type suppressions were removed, protocol callback
  exception boundaries are documented, and specific URL4 parse/render failures are translated.
  Every Candidate Result now preserves its inspected Operation projection in portable Report JSON,
  and all member/Failure operation references are validated against that projection.
- **Deviations:** production discovery/manifest decoding, imported-URL4 planning, compatibility
  preflight against a destination Engine, per-Candidate URL4 compilation, final Candidate Result
  decoding, Candidate scheduling/cache reuse, reconnect capability refresh, hosted authentication,
  and built-in rich runtime progress remain paused on unpublished external Engine contracts. No
  guessed fallback was added.
