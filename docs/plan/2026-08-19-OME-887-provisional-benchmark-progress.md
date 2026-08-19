# OME-887 — Implementation plan

1. Add a run-scoped Engine progress session and a non-droppable internal signal that maps onto the
   existing sequenced structured-log transport without changing `packages/url4`.
2. Instrument the generic Benchmark protocol at Candidate, Grading, and completed-Case boundaries.
   Register each Benchmark's existing aggregate adapter with the progress endpoint so provisional
   and final scoring share exactly one implementation.
3. Add strict Client decoding for the public immutable `BenchmarkProgress` Event, including count,
   coverage, finite-score, replay, and monotonic-accounting validation.
4. Extend Evaluation state to retain one progress snapshot per Candidate Run and render an honest
   completed-Case bar, live stage counts, score-so-far/coverage, and incomplete terminal state in
   notebook and text views.
5. Add cross-Benchmark conformance fixtures for IFEval, DRACO, and HealthBench; add multi-Candidate,
   malformed-event, light/dark HTML, replay, and no-event fallback tests.
6. Verify the latest local `screamingface-brand` progress pattern, run focused suites and both
   Engine and ScreamingFace stack gates, then record the exact outcome.
