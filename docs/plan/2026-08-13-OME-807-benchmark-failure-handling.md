---
title: Implement originals-faithful benchmark failure handling
ticket: OME-807
status: approved
date: 2026-08-13
spec: ../spec/2026-08-13-OME-807-benchmark-failure-handling.md
---

# Implement originals-faithful benchmark failure handling

The test surfaces are the strict producer models, the shared finalizer, and each installed
Benchmark adapter. Tests assert complete observable values rather than private helper calls.

1. Add red `CaseResult` and `CandidateResult` contract tests for graded refusals, refused grading
   failures, required top-level coverage, scored Candidates retaining ungradeable Cases, removal
   of canonical `metrics.coverage`, and rejection of contradictory/non-finite shapes. Evolve the
   unreleased V1 Pydantic models only after those tests fail for the intended reasons.
2. Add red finalizer tests for partial scoring, zero gradeable Cases, exact rounded coverage,
   Candidate-level Failures, trustworthy missing Cases, surplus/duplicate identities, and scorer
   input containing only numeric-grade Cases. Replace the OME-802 fail-closed implementation with
   the smallest policy satisfying that interface.
3. Add red Candidate Invocation/evaluation tests proving an exact provider refusal reaches the
   normal evaluator as answer text while remaining explicit metadata. Implement one shared
   `CandidateAnswer` representation; do not add per-Benchmark refusal branches.
4. Migrate IFEval end to end: carry refusal metadata through its exact check/Case-evaluation
   record, grade that text deterministically, construct the public refused Case, and score only
   gradeable Cases without changing official math.
5. Repeat the tracer slice for DRACO, preserving multi-pass Evidence requirements and reference
   scoring while removing only the Candidate-level 95% publication floor.
6. Repeat for HealthBench, preserving negative Case grades and the unclipped challenge mean so a
   refusal cannot gain an artificial universal-zero advantage.
7. Add cross-Benchmark conformance tests for successful, refused, partially unavailable, fully
   unavailable, and protocol-corrupt selections. Add/retain privacy tests for stack traces,
   credentials, Unix/Windows paths, and `key=value` secrets.
8. Run the focused suites and complete URL4 Cloud gate. Reconcile existing tests that assert the
   intentionally superseded fail-closed V1 shape, disclosing those fixture migrations rather than
   retaining compatibility code.
9. Review `origin/main...HEAD` for Benchmark-specific policy copied into adapters, Client or
   leaderboard scope, NaN, raw exception leakage, v2/legacy paths, and any successful-score drift.
