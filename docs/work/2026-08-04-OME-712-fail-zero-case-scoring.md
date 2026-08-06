---
ticket: OME-712
stack: url4-cloud
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-712 — Fail closed when DRACO scores no Cases

## Intent

Prevent a DRACO Evaluation that scores no Cases from returning a normal zero-valued
`CandidateResult`. The Aggregation boundary must raise a typed failure, and the installed Benchmark
route must expose it as `benchmark_unavailable`, so an infrastructure or Grading failure cannot be
misreported as Candidate performance.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/draco/aggregate.py`
- `apps/url4-cloud/tests/unit/test_draco_aggregate.py`
- `apps/url4-cloud/tests/unit/test_draco_aggregate_case_mapping.py`
- `apps/url4-cloud/tests/unit/test_benchmark_runtime.py`
- `docs/spec/2026-08-04-OME-712-benchmark-runtime-certification.md`
- `docs/work/2026-08-04-OME-712-benchmark-runtime-certification.md`
- `docs/work/2026-08-04-OME-712-fail-zero-case-scoring.md`

## Test plan

- RED at the installed URL4 Benchmark route: an empty row collection raises a permanent
  `ResolutionError` with code `benchmark_unavailable` instead of returning a result.
- Reverse the two prior unit assertions that explicitly required empty Aggregation to succeed. This
  is the owner-approved confidence-gate exception acknowledged before implementation; retain both
  tests as fail-closed assertions in their original behavioral contexts.
- Preserve successful full and sliced Case scoring, and preserve explicitly partial results where at
  least one Case scored; partial-result semantics are a separate owner decision.
- Run the focused DRACO/Aggregation tests, then the complete url4-cloud canonical gate.

## Acceptance

- `aggregate("[]", ...)` raises `AggregateError` containing `no Cases`.
- Any non-empty row set from which zero valid Case results can be produced also raises.
- The installed Aggregate route translates that error to permanent `benchmark_unavailable`.
- One-or-more scored Cases retain the current result schema and metrics.
- No GitHub, Linear, branch-stack, or paid-provider state changes.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** all seven planned files; no unplanned production surface.
- **Commits:** none planned; owner review first
- **Gates:** focused DRACO/Aggregation/runtime set 40 passed; canonical url4-cloud gate all green;
  full coverage run 773 passed, 10 skipped, 94.07% coverage, 129 warnings.
- **Deviations:**
  - Linear status was not mutated because the owner explicitly constrained this pass to local
    changes.
  - `run_gates.py` used `--skip-append-only` for the two owner-approved prior-test reversals. The
    exact files are `test_draco_aggregate.py` and `test_draco_aggregate_case_mapping.py`; both retain
    the old scenario while asserting the corrected fail-closed contract.
  - The first gate attempt found one formatter-only blank-line difference; Ruff formatted it and the
    second attempt was fully green.

## Wisdom and confidence review

- The single post-reduction guard is the smallest design that covers both empty input and non-empty
  input with no valid Case outcomes; no speculative partial-result policy was added.
- The installed URL4 route is the user-visible seam, with direct Aggregation tests preserving the
  arithmetic boundary. Tests assert error behavior rather than implementation calls.
- The public contract intentionally changes from a plausible numeric success to the existing typed
  failure channel. The owner approved that change and the necessary prior-test reversals.
- No dependency, schema, identity, secret, network, or persistence behavior changed. The change
  closes a fail-open path.
