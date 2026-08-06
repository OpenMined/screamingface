---
title: OME-712 — Engine benchmark foundation implementation plan
status: completed
created: 2026-08-06
ticket: OME-712
spec: docs/spec/2026-08-06-OME-712-engine-benchmark-foundation.md
---

# Engine benchmark foundation implementation plan

## Goal

Land the generic Engine extension seam required by future DRACO and IFEval runtimes without
installing a scored Benchmark or moving Benchmark semantics into URL4 or AI Gateway.

## Sequence

1. Define immutable Benchmark metadata, structured protocol builders, strict selection, and a
   static registry with explicit installer and asset-root injection.
2. Expose metadata-only list discovery and complete executable detail resources with deterministic
   conditional HTTP responses.
3. Install one Candidate Invocation adapter into the shared Runner `Url4Node`, carrying exact
   output, finish reason, and provider refusal fields.
4. Add task-local retrieval ceilings and terminal model-outcome recording without coupling the
   Connector to Benchmark definitions.
5. Enforce nested retrieval narrowing, pre-spend capability checks, Tavily exclusions,
   post-filtering, and direct-fetch blocking.
6. Validate every full Benchmark protocol and installed literal endpoint before the Runner world
   becomes executable.
7. Prove discovery, installation, composition, concurrency isolation, retrieval enforcement, and
   outcome preservation with focused tests, then run all URL4 Cloud quality gates.

## Landing boundary

- Modify only URL4 Cloud Engine code, its tests, and OME-712 artifacts.
- Defer scored protocols, case browsing, SDK/report behavior, deployment, authentication, budgets,
  and notebook behavior to their owning PRs.
- Update the inherited URL4 importer boundary test explicitly because Benchmarks are now an owned
  Engine extension that builds structured URL4. Disclose that deliberate append-only exception in
  the PR test plan.

## Verification

- Focused Benchmark foundation tests.
- URL4 Engine importer boundary and Engine/control-plane layering checks.
- Ruff lint and formatting, Pyright, and the complete URL4 Cloud test suite with coverage.
