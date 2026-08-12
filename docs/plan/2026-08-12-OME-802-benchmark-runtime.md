---
title: Implement generic benchmark outcome and scoring runtime
ticket: OME-802
status: approved
date: 2026-08-12
spec: ../spec/2026-08-12-OME-802-benchmark-runtime.md
---

# Implement generic benchmark outcome and scoring runtime

1. Add producer-contract tests for scored, refused, and failed Case Results and for strict nested
   Evidence, Check, Grade, and Failure shapes; implement the Pydantic values in
   `benchmarks.contract` only after each red test.
2. Add finalizer tests proving stable order, duplicate rejection, all-scored scorer invocation,
   canonical metric validation, and fail-closed refusal/failure behavior; implement
   `benchmarks.aggregation` minimally.
3. Add a DRACO refusal tracer test at its installed runtime route, then carry exact refusal into a
   typed refused Case without invoking grading. Migrate existing DRACO Case builders and aggregate
   finalization while preserving official scoring fixtures.
4. Repeat the refusal and typed-result tracer slice for canonical IFEval. Remove partial scoring:
   any selected failed/refused Case makes the Candidate unscored while retaining all Case details.
5. Repeat for HealthBench, preserving the unclipped score and rubric evidence semantics.
6. Add cross-Benchmark conformance tests that feed each aggregate equivalent scored and failed
   cases and assert the common v1 envelope, canonical metrics, exact Case count, and fail-closed
   behavior through the public producer/finalizer interfaces.
7. Run all existing URL4 Cloud tests, then the complete `url4-cloud` gate runner. Reconcile the
   pre-release tests that asserted partial scoring or the old shallow wire shape to the explicitly
   approved strict v1 contract; do not keep either behavior through a compatibility path.
8. Review `origin/main...HEAD` for copied Benchmark mechanics, speculative adapter registries,
   private rubric leakage, score fabrication, v2/legacy paths, and any URL4 or Client change that
   belongs in a separate landing.

The agreed test seams are the strict producer contract, generic Candidate finalizer, and each
installed Benchmark adapter. Tests observe those interfaces rather than private helper calls.
