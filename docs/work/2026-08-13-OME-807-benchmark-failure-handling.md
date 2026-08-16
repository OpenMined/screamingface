---
ticket: OME-807
stack: url4-cloud
status: complete
started: 2026-08-13
finished: 2026-08-16
---

# OME-807 — Implement originals-faithful benchmark failure handling

## Intent

Replace the shared fail-closed Candidate finalizer with an originals-faithful policy: normal
Benchmark grading for model behavior and exact refusals, typed missing grades for infrastructure
failures, loud protocol-integrity errors, and factual top-level coverage on every Candidate Result.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/contract.py` — evolve the strict unreleased V1 Case
  and Candidate Result invariants for graded refusals, partial scoring, and top-level coverage.
- `apps/url4-cloud/src/url4_cloud/benchmarks/aggregation.py` — partition gradeable Cases and
  centralize score/coverage publication without interpreting Benchmark failures.
- `apps/url4-cloud/src/url4_cloud/benchmarks/evaluation.py` — preserve evaluator-facing refusal
  text and exact refusal metadata through the shared Candidate seam.
- DRACO, IFEval, and HealthBench runtime/evaluation/aggregate adapters — carry the shared refusal
  fields and preserve each official checker and scorer.
- `apps/url4-cloud/tests/unit/` — producer contract, finalizer, cross-Benchmark refusal/partial
  failure, protocol integrity, score parity, and public-error privacy tests written first.
- SDLC task mirror, spec, plan, and this ledger.

## Test plan

- RED: exact refusals receive normal numeric grades for all three Benchmarks while public output
  remains null and exact refusal remains present.
- RED: one infrastructure failure lowers top-level coverage and does not erase the score from
  gradeable Cases; all failures yield the explicit zero-coverage unscored shape.
- RED: scorer adapters receive only numeric-grade typed Cases and retain official successful math.
- RED: surplus, duplicate, mismatched, forged, and ambiguous positional rows abort loudly.
- RED: sanitization rejects stack traces, credentials, filesystem paths, and key/value secrets.
- GREEN: all pre-existing successful Benchmark fixtures and the complete URL4 Cloud gate pass.

## Acceptance

- DRACO, IFEval, and HealthBench share one typed failure/finalization policy.
- Candidate/model behavior is graded by the Benchmark; infrastructure failures are excluded; only
  protocol corruption aborts.
- Candidate Result always declares factual top-level coverage and never serializes NaN.
- Exact refusal, grading Evidence, safe Failure detail, and every selected Case survive the wire.
- No second runner, Benchmark-manifest DSL, Client policy, legacy path, or schema version is added.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** the shared Benchmark contracts/finalizer/evaluation seam; the DRACO, IFEval,
  and HealthBench runtime, exact-envelope, and aggregate adapters; a shared Case Execution
  envelope carrying Case identity, Candidate Invocation, and the protected grading outcome;
  shared Case-record binding; strict Client score/coverage/outcome decoding and report rendering;
  public-error path sanitization; and focused cross-Benchmark and Client conformance tests.
- **Commits:** this unit's implementation commit (`Refs: OME-807`).
- **Gates:** `run_gates.py url4-cloud --base origin/main --skip-append-only` — **ALL GATES
  GREEN**: Ruff check, Ruff format, Pyright, layering, and pytest with coverage ≥80%. Direct full
  unit run: **1464 passed, 5 skipped** after the final identity regression (the gate reruns the
  same suite under coverage). `run_gates.py screamingface --base origin/main --skip-append-only`
  — **ALL GATES GREEN**: Ruff check, Ruff format, Pyright, pytest with coverage ≥95%, notebook
  validation, package build, and distribution inspection. Direct Client run: **851 passed, 1
  skipped**.
- **Deviations:**
  1. The append-only check was intentionally skipped under the owner's explicit confidence-gate
     decision to evolve the unreleased V1 contract in place with no legacy/fallback path. Existing
     assertions that required all-or-nothing scoring or universal refusal zeroes were migrated to
     the approved originals-faithful policy; none were silently removed or skipped.
  2. `benchmarks/errors.py` was deleted rather than retained as an unused compatibility module:
     exact refusals now remain normal evaluator input and public outcome data.
  3. No implementation deviation from the approved spec; Benchmark checking and score formulas
     remain owned by their existing adapters. The follow-up adds no URL4 language feature: it
     composes existing expression and collected-error primitives behind one shared Benchmark
     capability.

## Post-merge conformance audit (2026-08-16)

The latest-main audit found incomplete acceptance coverage rather than a new product direction:

- preserve a refused Candidate Invocation when a later checker or Judge fails before the Case
  envelope completes;
- enforce the producer's score/coverage/Case invariants independently in the Client decoder;
- reject every recognizable filesystem-path form at the public Failure seam;
- represent provider refusals without text explicitly instead of inventing provider evidence;
- exercise the same outcome matrix through DRACO, IFEval, and HealthBench adapters.

The follow-up implementation remains under the approved V1 spec and plan. Shared transport,
identity, outcome, and finalization mechanics belong in the generic Benchmark runtime; only each
Benchmark's checker, scoring, and safe-feedback semantics remain in its adapter.
