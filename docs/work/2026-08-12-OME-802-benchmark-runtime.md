---
ticket: OME-802
stack: url4-cloud
status: complete
started: 2026-08-12
finished: 2026-08-12
---

# OME-802 — Extract generic benchmark outcome and scoring runtime in URL4 Cloud

## Intent

Deepen the existing `CandidateResult` producer module into the single strict result seam used by
all Engine-owned Benchmarks. The module preserves every selected Case and explains whether it was
scored, refused, or failed; applies fail-closed Candidate finalization once; and leaves only the
published checker and scoring mathematics in DRACO, IFEval, and HealthBench adapters.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/contract.py` — strict nested producer models for
  Evidence, Checks, Case Grades, Failures, Case Results, and Candidate Results, evolving the
  unreleased `screamingface.candidate-result.v1` contract in place.
- `apps/url4-cloud/src/url4_cloud/benchmarks/aggregation.py` — one fail-closed finalization
  interface that invokes a Benchmark scorer only when every selected Case is scoreable.
- DRACO, IFEval, and HealthBench runtime/aggregate modules — retain exact refusals, construct the
  shared models, and supply their irreducible scoring adapters.
- `apps/url4-cloud/tests/unit/` — public-seam contract, finalizer, refusal, fail-closed, and
  cross-Benchmark conformance tests written before implementation.
- SDLC task mirror, spec, plan, and this ledger.

## Test plan

- RED: strict `CaseResult` tests for scored, refused, and failed outcomes; reject unexplained or
  contradictory shapes.
- RED: finalizer calls the scorer only for complete scored coverage and otherwise emits
  `score=None`, empty metrics, and every ordered Case.
- RED: each Benchmark preserves exact Candidate refusal and emits the same v1 Case shape.
- RED: malformed nested evidence/check/failure payloads fail at producer construction.
- GREEN: all pre-existing DRACO, IFEval, HealthBench, registry, and runtime tests pass without a
  second execution pathway or compatibility decoder.

## Acceptance

- Every selected Case is represented exactly once and in selection order.
- Incorrect scored answers, exact provider refusals, grading failures, and execution failures are
  distinguishable without inspecting logs or inferring from answer text.
- Candidate scoring is fail-closed whenever a required Case is not scored.
- All three Benchmarks construct the same strict nested producer models and retain open
  Benchmark-specific metrics.
- The wire remains `screamingface.candidate-result.v1`; there is no v2, legacy shape, alias,
  migration, dual writer, or fallback.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** strict nested contract and generic finalizer added; DRACO, IFEval, and
  HealthBench migrated; exact provider refusal survives URL4 collection; pre-release partial-score
  and shallow-envelope tests tightened in place; each Benchmark revision now incorporates the
  existing v1 result-contract identity.
- **Commits:** this change (`feat(url4-cloud): enforce benchmark result contract`)
- **Gates:** `ruff check`, `ruff format --check`, Pyright, layering, and the coverage gate pass;
  1,361 URL4 Cloud tests pass with 5 existing skips. The append-only policy check is intentionally
  skipped because this pre-release task replaces assertions for the old partial v1 contract rather
  than retaining that behavior through compatibility tests.
- **Deviations:** Existing tests were edited where they asserted the deliberately replaced
  unreleased v1 shape or partial-scoring policy. No compatibility implementation was added.
