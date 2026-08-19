---
ticket: OME-887
stack: repo
status: in_progress
started: 2026-08-19
finished:
---

# OME-887 — Benchmark-native provisional Evaluation progress

## Intent

Make long paid Evaluations visibly advance by Case and expose the Benchmark's truthful score over
the completed gradeable subset, independently for every Candidate.

## Planned changes

- `apps/screamingface-engine/.../benchmarks/` — shared progress session, protocol boundaries, and
  exact aggregate-adapter reuse for DRACO, IFEval, and HealthBench.
- `apps/screamingface-engine/.../runner/executor.py` — non-droppable internal signal to existing
  sequenced structured telemetry.
- `packages/screamingface/src/screamingface/{events.py,_engine,_ui}/` — strict public Event decode,
  per-Candidate state, and brand-aligned notebook/text presentation.
- focused Engine/Client contract and rendering tests.

## Test plan

- Cross-Benchmark provisional score equals the same subset passed through the final scorer.
- Null score with zero gradeable Cases; negative HealthBench score remains unchanged.
- Counts and coverage reject contradictions, regression, non-finite numbers, and double counting.
- Multi-Candidate runs remain distinct by root Run identity.
- Intermediate replay is idempotent and absence of progress Events preserves current fallback UI.
- Existing URL4 package is byte-for-byte untouched.

## Acceptance

- Every selected Case is represented exactly once across queued, Candidate, grading, and complete.
- Provisional score and coverage come from the Benchmark's authoritative aggregate implementation.
- Progress failures never change Candidate, grading, or final-result behavior.
- The Client renders every Candidate independently, with `complete / selected` controlling the bar.
- A transport-successful but unscored/partial Benchmark result is presented as incomplete.
- No Case material, rubric, prompt, or provider error enters the progress Event.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** shared Engine Benchmark progress adapter/session/protocol instrumentation and
  executor bridge; public Client Event decoding, state fold, notebook/text rendering; contract,
  replay, fallback, theme, and regression tests; spec/plan/task/ledger artifacts.
- **Commits:** this PR — `feat(benchmarks): stream provisional evaluation progress`.
- **Gates:** Engine unit suite: 1,728 passed, 6 skipped. SDK suite: 912 passed, 1 skipped.
  Focused cross-stack suites: 118 passed.
- **Deviations:** the initial segmented stage-occupancy bar was replaced after live review with the
  brand completion bar because one running Case otherwise rendered as 100% complete. Existing
  transport goldens and assertions are intentionally updated for the protocol revision; the PR
  must disclose the append-only override. No `packages/url4` change.
