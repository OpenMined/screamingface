# OME-825 — Benchmark refusal integrity (plan)

Spec: `docs/spec/2026-08-14-OME-825-benchmark-refusal-integrity.md`.
All changes in `apps/url4-cloud`; one PR; branch `OME-825-benchmark-refusal-integrity`.

## Changes, in dependency order

1. **contract.py**
   - `PROVIDER_REFUSAL_PLACEHOLDER` constant (the graded marker text).
   - `validate_candidate_outcome(answer, output, refusal, *, benchmark)` — the shared
     outcome-triple validator; error messages keep the exact per-benchmark wording.
   - `candidate_coverage(cases, case_count)` — the single coverage formula;
     `_candidate_outcome` compares against it.
   - `_require_failed_case`: drop the dead `provider_refusal` clause.
2. **aggregation.py** — `finalize_candidate_result` computes `coverage` via
   `candidate_coverage`.
3. **draco/records.py, healthbench/records.py** — `_validate_outcome` bodies replaced by
   delegation to `validate_candidate_outcome`.
4. **candidate.py** — in the `provider_refusal` interception, substitute
   `PROVIDER_REFUSAL_PLACEHOLDER` when the outcome carries no refusal text.
5. **ifeval/corrective_policy.py** — LANL_FLOW final clause gains "carrying the
   member's refusal marking" (the hash-derived variant revision changes with it;
   the v1 label stays — the variant is unreleased, nobody to signal).
6. **ifeval/iterative_correction.py** — member-record payload adds
   `"refusal": f"${check}.refusal"`.
7. **ifeval/runtime.py** — `_member` parses nullable `refusal` (mirrors `finish_reason`);
   `_attempt_member` requires it; `_lanl_select` encodes
   `("" if refusal else answer, finish_reason, refusal)`.
8. **ifeval/aggregate.py** — `_failure_stage` removed; stage is the literal `"grading"`
   with a WHY comment (collected url4 errors carry no code, so the prefix branch was dead).

## Tests

- `test_benchmark_foundation.py` (or the candidate adapter's home): null-text
  `provider_refusal` → placeholder refusal, empty output.
- `test_ifeval_iterative_correction.py`: all-members-refused selection carries refusal;
  member fixtures gain `refusal`; LANL expression/revision goldens updated.
- Contract tests: coverage helper; failed-case validator without the dead clause.
- Full `uv run pytest tests/unit` green.

## Risks

- LANL golden churn is deliberate (revision bump). If url4 `$ref.field` null
  substitution misbehaves for `refusal`, mirror the existing nullable
  `finish_reason` handling — same mechanism, already proven.
