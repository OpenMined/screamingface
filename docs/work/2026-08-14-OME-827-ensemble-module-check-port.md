---
ticket: OME-827
stack: url4-cloud
status: in_progress
started: 2026-08-14
finished:
---

# OME-827 — Lift corrective-loop substrate behind a check-surface port

## Intent

Make corrective execution benchmark-independent on the Engine: generic invocation and
control routes consume an advertised Benchmark check surface, while IFEval retains only
its irreducible deterministic checking semantics. The former IFEval corrective variants
are retired because candidate construction belongs to the Client Recipe.

## Planned changes

- Add the generic `benchmarks/ensemble/` runtime and install it in every Runner world.
- Advertise an optional typed `check_surface` in Benchmark resources.
- Adapt canonical IFEval to the check port and retire the two corrective registry variants.
- Preserve provider-refusal identity through generic selection.
- Cover the runtime decision table and one Client-compiled end-to-end expression.

## Test plan

- Gate/selection tests pin early exit, deterministic tie fallback, last-round selection,
  refusal preservation, malformed envelopes, and member labels beyond the old LANL limit.
- Manifest tests pin absent/free/paid check surfaces and exact route identity.
- Cross-stack goldens execute Client-produced CorrectiveLoop and SelfCorrective URL4.

## Acceptance

- Canonical IFEval accepts one whole corrective Candidate through the same `$candidate`
  seam as Model/Fusion/Pipeline.
- The Engine contains no IFEval-specific loop builder.
- A benchmark without a check surface cannot be used for mid-run checking.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** `apps/url4-cloud/src/url4_cloud/benchmarks/ensemble/`, Benchmark
  definition/runtime wiring, canonical IFEval adapter, retirement cleanup, and focused
  unit/cross-stack tests.
- **Commits:** PR #598 commits are recorded in the parent OME-796 ledger until squash.
- **Gates:** URL4 Cloud full gate green (Ruff, format, Pyright, layering, tests/coverage).
- **Deviations:** DRACO and HealthBench adapters ship separately in PRs #599 and #600;
  this PR owns the generic substrate and IFEval adapter only. Client-generated transport
  goldens were rebaked after retiring the LANL four-member label ceiling.
