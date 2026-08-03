---
ticket: OME-726
stack: repo
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-726 — Expose benchmark method selection in the SDK

## Intent

`sf.evaluate(..., benchmark="ifeval", method="single_pass")` and
`sf.benchmarks.get("ifeval", method=...)`; `method=None` = engine default
(corrective). Catalog display explains the methods so `sf.benchmarks.list()` teaches
the semantics. Notebook 07 reworked around the new default.

## Planned changes

- `_engine/benchmark.py` + `_evaluation/benchmark.py` — pass `?method=`, decode the
  additive method fields
- `client.py` / `_evaluation/runner.py` — keyword-only `method: str | None = None`
- `_engine/catalog.py` / display — `get(id, method=...)`; methods line in cards
- `scripts/build_notebooks.py` + regenerated 07 — default cell = corrective chain
  (3× cost note up front); `method="single_pass"` cell for the paper baseline
- SDK tests for method passthrough + display (additive)

## Test plan

- evaluate(method=...) reaches the resource fetch query; None omits the param
- decoder tolerates absent method fields (draco) and reads them when present
- notebook checks green

## Acceptance

- SDK gates green; live e2e: corrective default and single_pass both return
  `Report(ok=True)` with the right call counts (3×/1× per case)

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus TWO wrapper layers the plan missed and the live
  e2e caught: module-level `sf.evaluate` (`_default_client.py`) and module-level
  `sf.benchmarks.get` (`benchmarks.py`) — both grew the `method` kwarg. New
  `tests/test_benchmark_method_selection.py` (4 tests: no-param-when-omitted
  invariant, variant fetch, evaluate passthrough, blank-method rejection). Prior-test
  change: OME-724's delegation stub tracks the grown `get` signature (pre-declared
  class of change).
- **Commits:** `2a3be1fd` feat: add SDK method selection and the CorrectiveEnsemble recipe (pushed to upstream/OME-605-screamingface-client-v1).
- **Gates:** SDK ruff/format/pyright green, 381 tests passed, notebook checks green
  (07 regenerated: evaluate cell = `method="single_pass"` with a method-explainer md
  so the on-ramp stays 1-call-per-case; corrective default explained inline).
  Coverage gate still pre-existing red (<95) on the branch.
- **E2E:** live — default evaluate ran the chain (1548 out-tokens), `method=
  'single_pass'` ran the paper protocol (427 out-tokens), browse returns the right
  per-method revisions.
- **Deviations:** the two wrapper layers above; found because the acceptance test was
  a REAL run, not just the unit suite.

## Post-unit amendment (2026-08-03, owner-directed)

Notebook 07 reworked corrective-FIRST for a fresh researcher: default evaluate cell
runs the chain (`limit=3` → 9 calls, cost note up front), followed by four "Observe"
sections — pass@attempt (the single-pass baseline hiding inside the run), the
readable url4 plan (count attempt/check slots, verdict threading, revision-in-routes),
a corrective-vs-single_pass cost comparison cell, and an aggregate raw-event trace
(`Counter` over span names, with the semantic-events limitation named). Regenerated;
`check_notebooks.py` + ruff green. Full live cell-run NOT completed by the agent —
the engine instance running at verification time served a model catalog without the
notebook's haiku route (likely started outside the worktree); owner runs the notebook.
