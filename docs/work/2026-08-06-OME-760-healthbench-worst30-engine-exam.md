---
ticket: OME-760
stack: url4-cloud
status: in_progress
started: 2026-08-06
finished:
---

# OME-760 — Add the healthbench-worst30 engine exam (per-item GPT-5.4 judging, unclipped mean)

## Intent

Onboard HealthBench onto the SF engine as the entry-challenge exam: 157 hardest
HealthBench Professional rows (team-picked worst-30%), per-rubric-item GPT-5.4 judging
byte-congruent with OpenAI simple-evals, unclipped-mean challenge scoring. Built against
`integration/keelan-all-changes-20260806` (Keelan's frozen client→benchmark flow); design
`.dk/plans/2026-08-05-healthbench-sf.md`; epic `OME-759`.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/healthbench/__init__.py`
- `…/healthbench/prompts.py` — official GRADER_TEMPLATE verbatim
- `…/healthbench/subset.py` — frozen 157 HF ids + provenance
- `…/healthbench/prepare.py` — bake all 525 rows: public cases.json (chat envelopes) +
  private rubric assets; asserts subset ids present, ≥1 positive item per row
- `…/healthbench/definition.py` — pins, REVISION, routes, `_build()`, WORST30 + SMOKE
  Benchmark entries (`case_ids`)
- `…/healthbench/runtime.py` — install(): cases data route, rubric-tasks, rubric-verdict,
  aggregate; install-time asset preflight
- `…/healthbench/verdict.py` — judge-reply parse (strict bool), engine-bound ids
- `…/healthbench/scoring.py` — case score (achieved/Σpositive, unclamped), unclipped mean,
  sample stdev
- `…/healthbench/aggregate.py` — reducer; missing-asset row fails loudly (B1 rule);
  verdict_coverage
- `apps/url4-cloud/src/url4_cloud/benchmarks/__init__.py` — registry entries
- `apps/url4-cloud/tests/unit/test_healthbench_*.py` — suites per design §4.8

## Test plan

- Registry/manifest: resource shape, revision stability, ids `healthbench-worst30` /
  `healthbench-smoke`, case_ids wiring.
- prepare: subset-id freeze (missing id = loud), chat envelope shape, rubric privacy
  (no rubric text in cases.json), positive-item invariant.
- verdict: fenced/bare/malformed/prose replies; strict-bool ("true" string rejected).
- scoring: `[7]` int rendering; negative points subtract; unclamped row score; unclipped
  mean; sample stdev (n−1).
- aggregate: partially-populated assets dir → failed-case result, never silent drop
  (invariant: a judge/asset failure can only LOWER validity, never inflate the score);
  verdict_coverage gates validity.
- expression: GRADER_TEMPLATE survives `_url4_text`; judge call has empty intent (no
  system message); rendered size measured.
- e2e stub trace: 1 case → candidate once → N judge calls → aggregate.

## Acceptance

- `run_gates.py url4-cloud` ALL GREEN (free tests only — no live model calls).
- Both variants appear in the benchmark resource with distinct revisions and honest
  descriptions (worst30 labeled "challenge metric — not an official HealthBench score").
- DRACO/IFEval tests untouched and green.
- NO commits/pushes — Khoa reviews the working tree first (his instruction 2026-08-06).

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus `records.py` (Case/Rubric record binding, draco
  parity) and `case_evaluation.py` (envelope validation); tests consolidated into 5
  files (`test_healthbench_{definition,grading,aggregate,prepare,runtime}.py` — grading
  covers prompts+verdict+scoring). Registry-inventory tests extended (their designed
  maintenance path): `test_flat_benchmark_resources.py` id set,
  `test_url4_executor.py` url4-importer allowlist, `test_aigateway_connector.py`
  `_BENCHMARK_ROUTES`.
- **Commits:** none — Khoa reviews the working tree first (his instruction 2026-08-06).
- **Gates:** ruff ✓ · format ✓ · layering ✓ · pytest 1002 passed / 5 skipped, coverage
  92.21% (≥80) ✓ · pyright scoped to healthbench src+tests: 0 errors ✓. Full-repo
  pyright is RED on 3 PRE-EXISTING errors in `test_draco_aggregate.py:391` and
  `test_draco_failure_integrity.py:197` — present at the integration branch tip,
  untouched by this unit; left for Keelan's re-split.
- **Deviations:**
  - `chat_input()` is NOT used for baked case inputs — it renders a url4 struct for
    expression authoring; `cases.json` needs the plain-JSON envelope (`prepare.envelope`).
    Found by the runtime byte-parity test.
  - Smoke variant added (`healthbench/smoke`, 1 pinned in-subset Case) per the branch's
    lite/smoke house style — was a §7 design addition, confirmed in scope.
  - Verdict parsing accepts a preambled JSON object (draco's `_first_json_value`
    fallback) — parse-robustness only; strict-bool acceptance unchanged.
  - **Post-audit fix (2026-08-06):** an independent congruence audit found `;retry=2`
    never fired on the reference's retry condition — a malformed judge reply is a
    SUCCESSFUL model call, and the sibling wiring retried nothing (one bad JSON among
    ~3,700 judge calls would void a whole paid run). Fixed: judge call NESTED in the
    verdict route's context (`verdict.call`, draco shape), verdict raises TRANSIENT
    `judge_reply_invalid` on an invalid reply, `;retry=2` on the verdict source —
    engine-verified that each retry redraws a FRESH judge sample (2 new tests:
    fresh-sample retry ×3 calls; exhausted retries fail loudly). Also from the audit:
    scoring stdev docstring now names the bootstrap-std reporting deviation vs
    simple-evals; design doc updated (JUDGE_PARAMS web_search, nested expression
    sketch). Post-fix gates: pytest 1004 passed / 5 skipped, cov ≥80 ✓; scoped
    pyright 0 errors ✓; ruff/format ✓.
