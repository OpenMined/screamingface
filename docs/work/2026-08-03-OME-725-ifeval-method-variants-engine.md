---
ticket: OME-725
stack: url4-cloud
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-725 — Merge corrective chain into ifeval as method variants (engine)

## Intent

Owner decision: the registry holds real benchmarks only — `{draco, ifeval}`. The
corrective chain is `ifeval`'s DEFAULT method (the LANL reproduction is the point);
single-pass is `method="single_pass"` (paper-comparable). One exam, two protocols,
explicitly labeled incomparable. Reworks the uncommitted OME-721 output.

## Planned changes

- `benchmarks/definition.py` (SHARED — flag for Keelan): `BenchmarkMethod` value
  (name, revision, build) + optional `Benchmark.methods` tuple + `default_method`;
  `resource(limit, method=None)` selects a variant, rejects unknown methods; manifest
  gains additive `method`/`methods`/`default_method` ONLY when variants exist
- `benchmarks/ifeval/corrective.py` — drops its own Benchmark value; exports the
  corrective build + revision as a variant; aggregate reports `benchmark_id="ifeval"`
- `benchmarks/ifeval/definition.py` — IFEVAL carries both methods, default corrective
  (top-level revision/build = corrective's); description explains the default, the
  incomparability with published single-pass numbers, and the 3× cost
- `benchmarks/ifeval/runtime.py` — ifeval's install registers BOTH aggregates
- `benchmarks/__init__.py` — registry back to two entries
- `rest/benchmarks.py` — `?method=` query param (404-problem on unknown); listing
  entries expose methods + default when present
- Tests: rework the uncommitted corrective tests + the committed ifeval manifest
  block (directed redesign — pre-declared here); draco tests untouched and green

## Test plan

- resource(method=None) == corrective url4/revision; method="single_pass" == R0's
  exact url4/revision; unknown method raises/404s
- draco manifest byte-identical (no method fields)
- listing entry for ifeval carries methods + default; draco entry unchanged
- executable gates: corrective path (3 calls, pass@attempt) AND single-pass path
  (1 call) both under benchmark_id "ifeval"

## Acceptance

- `run_gates.py url4-cloud` green; live e2e both methods via SDK (OME-726)

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, except `corrective.py` was FOLDED into
  `ifeval/definition.py` and deleted (avoids a circular import; family stays one
  module, 220 lines). `BenchmarkMethod` + `methods`/`default_method` +
  `resource(limit, method)` landed in shared `benchmarks/definition.py` with
  `__post_init__` invariants (unique names; default named; top-level revision ==
  default method's).
- **Commits:** `86538e90` feat: add IFEval corrective method and candidate verifier actions (pushed to upstream/OME-605-screamingface-client-v1).
  uncommitted for review; nothing pushed.
- **Gates:** `run_gates.py url4-cloud --skip-append-only` ALL GREEN (697 unit tests,
  cov ≥80). Prior-test changes: manifest ifeval blocks reworked to the new default
  (directed redesign, pre-declared); listing test grew the conditional method fields.
- **E2E:** live catalog shows `ifeval methods=[corrective, single_pass] default=
  corrective`; draco entry unchanged. `sf.evaluate(haiku, 'ifeval', limit=1)` →
  corrective (1548 out-tokens, revision 22ca96fe…); `method='single_pass'` → 427
  out-tokens, revision 047f1de4… (R0's exact revision — proof the paper protocol is
  byte-identical).
- **Deviations:** none beyond the corrective.py fold.
