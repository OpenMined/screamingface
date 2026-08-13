---
ticket: OME-804
stack: url4-cloud
status: done
started: 2026-08-12
finished: 2026-08-13
---

# OME-804 — Extract generic benchmark evaluation capabilities in URL4 Cloud

## Intent

Move repeated Benchmark Evaluation mechanics behind a small URL4 composition/runtime interface so
future Benchmarks reuse trusted Engine capabilities while DRACO, IFEval, and HealthBench retain
their published evaluator and scoring semantics.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/` — shared protocol and runtime capabilities.
- DRACO, IFEval, and HealthBench definitions/runtime adapters — compose those capabilities and
  delete replaced plumbing.
- `apps/url4-cloud/tests/` — public-seam tracer and cross-Benchmark conformance coverage.
- OME-804 task mirror, spec, plan, and this work ledger.

## Test plan

- RED: shared outer protocol preserves selection order, collected failure, and aggregate intent.
- RED: two distinct installed evaluator adapters pass through the same runtime envelope.
- Existing Benchmark fixtures pin Candidate inputs, Judge/check behavior, evidence, Case scores,
  aggregate metrics, and direct URL4 replay throughout migration.
- Full URL4 Cloud gates and coverage run after the final slice.

## Acceptance

- Generic mechanics live once outside Benchmark-specific directories.
- Each Benchmark retains only its irreducible protocol semantics and thin adapters.
- Existing successful and failure outcomes remain equivalent through the public seam.
- No alternate runner, manifest DSL, version proliferation, or compatibility path is introduced.

## Outcome

- **Actual files:** Added shared `benchmarks/protocol.py` and `benchmarks/evaluation.py`, migrated
  the DRACO, IFEval (canonical and corrective), and HealthBench definitions/runtime adapters,
  added two cross-Benchmark public-seam test modules, and recorded the OME-804 task/spec/plan.
- **Commits:** One OME-804 implementation commit follows merged prerequisite PR #572; Khoa's two
  HealthBench fixes remain in `main` ancestry rather than being duplicated in this branch.
- **Gates:** `python3 .claude/scripts/run_gates.py url4-cloud --base origin/main` — all gates green
  (append-only tests, Ruff lint/format, Pyright, layering, and the full pytest coverage suite).
- **Review:** Independent Standards and Spec reviews are clean. Exact canonical URL4 is pinned for
  all three Benchmark families, malformed aggregate bounds fail with bounded public errors, and
  shared JSON, Case Evaluation, Candidate Invocation, and Aggregation mechanics live in the common
  runtime.
- **Deviations:** No generic evaluator registry was introduced. Existing evidence showed that the
  complete per-Case URL4 node and its revision-pinned installed routes already form the deeper
  evaluator seam; Benchmark-specific checking, prompts, retries, evidence validation, and score
  mathematics remain local.
