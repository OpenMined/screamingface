---
ticket: OME-825
stack: url4-cloud
status: in_progress
started: 2026-08-14
finished:
---

# OME-825 — Benchmark refusal integrity + PR #584 review cleanups

## Intent

Adversarial review of PR #584 (OME-807 failure policy, merged 2026-08-13) confirmed two
scoring-integrity bugs — both seams where the policy's "refusal is data, carried
end-to-end" doctrine leaks — plus three cleanups. A provider content-filter refusal with
null refusal text is published as a scored plausible-zero, and the IFEval LANL ensemble
republishes a refused member's refusal prose as a normal scored output. This unit closes
all five findings so refusals are always visible and attributable on the leaderboard.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/candidate.py` — null-text provider refusal
  gets a named placeholder refusal text instead of `output="" refusal=None`.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py` — LANL
  member records carry `refusal` from the check record.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/runtime.py` — member schema parses
  `refusal`; malformed refusal/answer mismatches fail before selection; `_lanl_select`
  re-encodes the chosen member's refusal instead of `None`.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/corrective_policy.py` — LANL protocol
  revision v2 + LANL_FLOW clause naming refusal carriage.
- `apps/url4-cloud/src/url4_cloud/benchmarks/contract.py` — shared
  `validate_candidate_outcome` + `candidate_coverage` helpers; drop the dead
  `provider_refusal` clause in `_require_failed_case`.
- `apps/url4-cloud/src/url4_cloud/benchmarks/aggregation.py` — coverage via shared helper.
- `apps/url4-cloud/src/url4_cloud/benchmarks/{draco,healthbench}/records.py` — delegate
  outcome validation to the shared helper.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/aggregate.py` — remove the dead
  `provider_`/`aigateway_` stage heuristic.
- Tests: new refusal-integrity tests + updated LANL protocol goldens.

## Test plan

- Candidate adapter: a `provider_refusal` error carrying `refusal=None` encodes an
  invocation with the placeholder refusal and empty output — WHY: a safety-filter event
  must never be indistinguishable from a legitimate empty answer (the "plausible zero").
- LANL select: when every member refused, the selected invocation decodes with the
  member's refusal text carried — WHY: selection may choose but must never launder a
  refusal into a scored output.
- LANL member validation: a refusal differing from the checked answer fails loudly —
  WHY: selection must never score one text and publish another.
- Contract: `candidate_coverage` is the single formula (producer and validator agree by
  construction); failed-Case validation unchanged for all real producers.
- Existing draco/healthbench records suites stay green with identical error messages.

## Acceptance

- All five OME-825 findings closed; full url4-cloud unit suite green; draco/healthbench
  protocol expressions byte-identical; only the LANL variant revision changes.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus test updates: `tests/unit/test_benchmark_foundation.py`
  (null-text refusal placeholder test), `tests/unit/test_ifeval_lanl_ensemble.py`
  (refusal-carrying selection and mismatch-rejection tests + member fixture gains `refusal`),
  `tests/unit/test_ifeval_member_shape.py` (fixture gains `refusal`),
  `tests/unit/test_ifeval_unscored_results.py` (failure stage pinned to `grading` with WHY).
- **Commits:** three commits on `OME-825-benchmark-refusal-integrity`; the third adds the
  refusal/answer integrity guard found during final review (PR carries the shas).
- **Gates:** `run_gates.py url4-cloud` green: append-only test check, ruff check +
  format, pyright, layering, and coverage floor; direct full suite 1407 passed / 5 skipped.
- **Deviations:** ifeval's dead stage heuristic became a constant `"grading"` with a WHY
  comment (behavior identical — the prefix branch was unreachable); the hand-fed-code
  test now pins `grading` for collected candidate failures. `_record_content`'s drifted
  ifeval predicate left as-is (structurally different record, no `output` field).
