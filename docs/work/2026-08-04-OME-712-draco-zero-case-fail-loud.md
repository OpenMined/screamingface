---
ticket: OME-712
stack: url4-cloud
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-712 — Make zero-case DRACO runs fail loudly

## Intent

Prevent a DRACO execution that scored no cases from looking like a legitimate zero-scoring
Candidate. If the selected row set is empty, or every row failed before producing a valid judge
verdict, aggregation must raise an execution-facing benchmark error with bounded diagnostics.

## Planned changes

- Correct the two existing empty-row expectations in DRACO aggregate tests.
- Add coverage for an all-failed row set and preservation of its collected in-band error.
- Add the minimal zero-scored-case guard to the DRACO reducer.

## Test plan

- Empty JSON row array raises `AggregateError` instead of returning `case_count=0` and `score=0`.
- Rows whose judge work all failed raise and include a sanitized collected error.
- A genuine evaluated case may still legitimately score zero.
- Partial success still returns scored cases plus explicit failures.

## Acceptance

- No successful DRACO result can contain zero scored cases.
- Operational failure cannot masquerade as Candidate quality.
- Diagnostics remain bounded and preserve useful collected URL4 error context.

## Outcome

- **Actual files:** `benchmarks/draco/aggregate.py` rejects an empty row collection and any
  all-failed collection, preserving up to three sanitized in-band errors; the aggregate and
  mapping suites correct the old empty-result expectation and cover a genuine evaluated zero.
- **Commits:** this focused restack commit (`fix(url4-cloud): reject unscored DRACO runs`)
- **Gates:** RED proved both unsafe paths; 37 focused DRACO aggregate tests passed; complete
  `run_gates.py url4-cloud --skip-append-only` lane green (Ruff, format, Pyright, layering, full
  coverage suite).
- **Deviations:** two pre-existing tests encoded the unsafe zero-result behavior. Their deliberate
  correction was explicitly approved by the user as part of this cleanup, so the append-only
  precheck was skipped and must be called out in review. No issue was created.
