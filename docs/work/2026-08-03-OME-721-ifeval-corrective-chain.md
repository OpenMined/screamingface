---
ticket: OME-721
stack: url4-cloud
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-721 — Build R1 corrective-loop IFEval variant (single-candidate MVP)

## Intent

The LANL reproduction's first runnable rung: `benchmark="ifeval-corrective"` runs each
case through a bounded 3-attempt corrective chain — answer → deterministic check →
violations feed the retry — and reports pass@attempt. Single candidate only (the
multi-member `CorrectiveEnsemble` recipe is a follow-up gated on the Keelan check-route
contract chat). Accuracy claims only; attempts 2–3 always execute (R2 cost caveat).
Syntax risk retired by the notebook-07 probe (named siblings + grade→action route).

## Planned changes

- `benchmarks/ifeval/grading.py` — `describe_failures(...)`: deterministic
  natural-language descriptions of failed instructions (verifier's own
  `build_description` output) for the feedback path
- `benchmarks/ifeval/runtime.py` — check intent accepts `<case>` or `<case>:<attempt>`;
  record gains additive fields `attempt`, `answer` (echo), `violations` (R0 aggregate
  ignores extras)
- `benchmarks/ifeval/corrective.py` — NEW: `IFEVAL_CORRECTIVE = Benchmark(...)`:
  `MAX_ATTEMPTS=3`; REVISION = hash(ifeval REVISION + corrective protocol tag); chain
  `_build()` (per case: attempt N's candidate input carries the prior check record);
  own `/benchmarks/ifeval-corrective/<rev>/aggregate` route; cases/check REUSED from
  the plain exam (install reads the sibling `ifeval` assets dir — one prepare covers
  both; documented INVARIANT)
- `benchmarks/ifeval/aggregate.py` — `aggregate_corrective(...)`: records grouped per
  row by attempt; selected = earliest strict-pass else last attempt; score =
  prompt-level strict accuracy on selected; metrics add `pass_at_1/2/3` (cumulative),
  `corrected_cases`; SDK contract held (`failures=[]`, exact case_count, flat numerics)
- `benchmarks/__init__.py` — register `IFEVAL_CORRECTIVE`
- `tests/unit/test_ifeval_corrective.py` — NEW; plus additive blocks in
  `test_benchmark_manifests.py` (corrective resource: candidate appears 3× per case,
  no model routes) and `test_aigateway_connector.py` `_BENCHMARK_ROUTES` (+1 route)
- `packages/screamingface/scripts/build_notebooks.py` + regenerated notebook 07 — live
  R1 section (evaluate `ifeval-corrective`, limit=2, per-attempt metrics) — OME-720
  extension, noted in both tickets
- VERIFY during build (Q13c): `/candidate` `max_invocations` accommodates
  3 × case_count

## Test plan

- RED first:
  - grading: `describe_failures` returns the failed instructions' official description
    text, empty for all-pass
  - runtime: intent `"7:2"` → record `case_id=7, attempt=2`; bare `"7"` → attempt 1;
    malformed attempt → benchmark_unavailable; record echoes `answer` and lists
    `violations` only for failed instructions
  - corrective aggregate: case passing at attempt 1 → selected 1, pass_at_1 counted;
    fail-fail-pass → selected 3, corrected_cases counted; never-pass → selected last,
    scored 0 for prompt-strict; recordless row → fail-all fallback, failures stays [];
    metrics flat numeric; case_count exact
  - manifests: corrective resource is valid `benchmark.v1`; url4 contains the plain
    exam's check route 3× per case and zero model routes; `required_models: []`
  - executable gate: linked fake candidate through `build_aigateway_world` — responder
    fails attempt 1 (comma), corrects on feedback; assert exactly 3 model calls per
    case (unrolled — even after a pass), final score 1.0, `pass_at_1 == 0`,
    `corrected_cases == 1`
- All prior tests stay green and unmodified (connector route-set extension is additive)

## Acceptance

- `run_gates.py url4-cloud` all green; notebook checks green
- Live e2e: `sf.evaluate(haiku, benchmark="ifeval-corrective", limit=2)` against local
  gateway+engine returns `Report(ok=True)` with per-attempt metrics
- R0 `ifeval` scores unchanged (registry sibling, zero shared-code behavior change)

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned. `install_corrective` landed in `runtime.py` (not a
  separate module); corrective aggregate identity is strictly positional (row N =
  case N) with exact instruction-id matching as the anti-forgery gate.
- **Commits:** `86538e90` feat: add IFEval corrective method and candidate verifier actions (pushed to upstream/OME-605-screamingface-client-v1).
  (R0 committed locally: b2bddc7a / 48636d26 / 91576df3 / d87f828f; nothing pushed).
- **Gates:** `run_gates.py url4-cloud --skip-append-only` ALL GREEN (ruff, format,
  pyright, layering, pytest 704 passed / cov ≥80). SDK: 377 passed, notebook checks
  green. Append-only skip covers additive appends + the shared `_ifeval_assets`
  fixture gaining a second case (behavior-preserving for prior tests) + the
  pre-declared connector route-set extension.
- **E2E:** live `sf.evaluate(haiku, benchmark="ifeval-corrective", limit=2)` →
  `ok=True`, score 1.0, pass_at_1/2/3 = 1.0 (haiku needed no correction live; the
  correction path is proven by the executable-gate test whose scripted candidate
  fails attempt 1 and corrects on verifier feedback — exactly 3 calls/case,
  corrected_cases=1). Unrolled cost visible: ~3× R0 tokens per case.
- **Deviations:**
  1. **NEW url4 lesson (repro: scratchpad edge_probe5):** context PROSE ships
     unescaped — a single quote in context text corrupts the rendered expression's
     re-parse (checks execute with raw `$refs`, siblings drop); top-level commas
     split contexts into slots. `_RETRY_INSTRUCTION` is quote/comma-free with an
     import-time invariant guard. Same bug class as the `@` holdings lesson — flag
     upstream to Kevin/Ionesio (renderer should escape or reject context prose).
  2. Tokens-per-attempt deliberately NOT in the result schema — gated on Q10 event
     fields `(case_id, member, role, attempt)`; pass@attempt ships now as flat
     metrics on unchanged `candidate-result.v1` (decision recorded in-session).
  3. Notebook R1-live section rides OME-720's builder (same generated notebook) —
     noted in both tickets rather than a separate pkg sub-issue.

## Post-unit amendment (2026-08-03, owner-directed)

The two notebook-07 sections this unit added ("R1 preview" syntax probe + "R1 live")
were MOVED out of `07_ifeval_e2e.ipynb` into the personal deep-dive
(`.dk/refs/benchmarks/IFEval/notebooks/ifeval_deep_dive.ipynb` §9–§10, untracked) —
owner call: too much engine internals for the researcher on-ramp; 07 now ends at the
Report inspection cells. `build_notebooks.py` trimmed, examples regenerated,
`check_notebooks.py` + ruff + pytest (377) re-verified green. The
`ifeval-corrective` benchmark itself is unchanged.
