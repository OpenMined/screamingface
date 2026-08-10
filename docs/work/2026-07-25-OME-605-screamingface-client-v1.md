---
ticket: OME-605
stack: screamingface
status: in_progress
started: 2026-07-25
finished:
---

# OME-605 — Implement the ScreamingFace Python Client v1

## Intent

Introduce the first public `screamingface` Python package with one coherent interface for
authoring Model and Fusion Candidates, discovering an Engine's executable resources, running an
Engine-owned Benchmark, and inspecting an immutable evaluation Report.

The Client owns Python ergonomics, URL4 Candidate compilation and linking, transport, progress,
and typed result decoding. The Engine owns Cases, Candidate invocation policy, grading,
aggregation, benchmark revisions, and the resulting benchmark URL4 expression.

## Implemented scope

- Immutable `Model`, `Fusion`, `Recipe`, discovery, operation, Event, CaseResult, and Report values.
- Lazy module-level helpers plus explicit synchronous and asynchronous Client lifecycles.
- Engine-backed Model, model-parameter, Benchmark, and provider-connection discovery.
- Provider API-key and OAuth connection flows without persisting provider credentials in the
  Client.
- Hosted Cloudflare Access login with the transferred application token held only in process
  memory.
- Generic Candidate compilation and structural linking against the bindings referenced by an
  Engine-supplied `screamingface.benchmark.v1` expression.
- Direct `evaluate(...)` execution over the Engine's REST/WebSocket lifecycle, including bounded
  replay, best-effort cancellation, and ordered typed Events.
- Built-in terminal and notebook progress that cannot abort a paid Run if rendering fails.
- Lossless Candidate and Case artifacts, including output, provider finish reason, deterministic
  or model-produced evidence, failures, usage, timing, and the exact executed URL4.
- Nested JSON benchmark metrics such as DRACO axis scores.
- Deterministically generated, no-spend-by-default quickstart and DRACO notebooks.

## Boundaries and non-goals

- There is no Client-side benchmark implementation, grading fallback, embedded fixture runtime,
  or dispatch on names such as `draco`, `draco/lite`, or `draco/smoke`.
- A Benchmark id is always explicit. The SDK does not invent a default Benchmark or reinterpret
  `limit` as a protocol variant.
- Candidate-owned prompts and model parameters cannot alter Benchmark-owned Judge routes,
  prompts, retrieval policy, grading, or aggregation.
- Provider refusals are captured deterministically from provider fields. The Benchmark decides
  whether a refused Case is scored; the Client does not use a fuzzy soft-refusal classifier.
- Member-level usage, timing, and failures remain `null` until the Engine publishes stable
  operation/member attribution.
- IFEval protocols and notebooks are outside the DRACO MVP presentation. The generic Fusion and
  linking interfaces remain benchmark-independent.
- Spend estimation, budget enforcement, leaderboard submission, and a tagged PyPI publishing
  workflow are separate follow-up work.
- This package is unreleased, so the implementation contains no legacy aliases, compatibility
  fallbacks, or migration behavior.

## Dependency status

- URL4 runtime foundations: merged in #517.
- AI Gateway model/provider/search contracts: merged in #520.
- Engine model-parameter proxy: merged in #522.
- Engine provider connections: merged in #524.
- Engine executable-model catalogue: #535 is open.
- Generic Engine benchmark foundation: #526 is open and follows #535.
- DRACO protocol and benchmark deployment remain a separate PR after the foundation.
- The Client PR will be reconstructed as a client-only diff from the resulting `main`; the
  consolidated preparation branch is not its review ancestry.

## Verification

- Ruff check and format pass.
- Pyright reports zero errors.
- 533 tests pass, one opt-in live integration is skipped, and aggregate coverage is exactly
  95.00% against a required 95% floor.
- The three generated notebooks match their builder and contain no execution outputs.
- Wheel and source distributions build as `screamingface==0.1.0` and pass the distribution-content
  check.
- A wheel installed into an isolated environment imports successfully and resolves the published
  `url4>=1.3.0` dependency.

## Remaining work

- Reconstruct the exact client-only branch on the final prerequisite merge base.
- Run the repository Standards and Spec review against that fixed diff.
- Run the requested `$grill-me` before publishing the draft PR.
- Fill `finished` and mark this ledger `done` only when the client PR is ready to merge.
