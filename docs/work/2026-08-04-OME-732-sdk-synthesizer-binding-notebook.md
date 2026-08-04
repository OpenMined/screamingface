---
ticket: OME-732
stack: screamingface
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-732 — SDK: universal Candidate bindings + Benchmark Family selection + notebook 07

> **Final contract update:** ADR 0003 replaced the per-shape `members=N` fetch described in the
> original plan/outcome below. The SDK now fetches one
> `screamingface.benchmark-family.v1` resource, selects the requested Variant locally, and links
> `$candidate_members` plus `$candidate_synthesizer` as universal bindings. The earlier text is
> retained as implementation history, not as current API guidance.

## Intent

SDK half of the two-benchmark pattern: satisfy the engine's `$candidate_synthesizer`
binding from a Fusion's synthesizer, tell the engine the candidate's member count at
benchmark fetch, and ship notebook 07 as the minimal 2x2 grid (done first as UX mock).

## Planned changes

- `_evaluation/candidate.py` — expose the synthesizer expression alongside member
  expressions
- `_evaluation/linking.py` — `$candidate_synthesizer` universal binding; loud
  candidate_shape_mismatch when required but absent
- benchmark fetch carries `members=N` (runner/engine adapter)
- `scripts/build_notebooks.py` — minimal 2x2 notebook (landed 2026-08-04 as UX-first)
- Tests: linker binding satisfaction, shape-mismatch errors, members param on fetch,
  notebook check

## Test plan

RED first: benchmark url4 referencing `$candidate_synthesizer` + Fusion links the
synthesizer expression; solo Model against it fails with candidate_shape_mismatch;
Fusion without synthesizer fails naming the fix; fetch query carries members=N.

## Acceptance

SDK suite + check_notebooks green; draco/canonical linking byte-identical.

## Outcome

- **Actual files:** linking.py ($candidate_synthesizer binding + candidate_shape_mismatch
  naming the fix; complexity split into _synthesizer_bindings), candidate.py
  (synthesizer_expression compiled from the Fusion's synthesizer or the catalog
  default), runner.py + compilation.py (ONE FETCH PER DISTINCT CANDIDATE SHAPE —
  contract change from one-fetch-per-evaluation; unknown shapes fall back to the first
  resource), _engine/benchmark.py (members query param), build_notebooks.py (minimal
  2x2 notebook, 16 cells), test_shape_adaptive_linking.py (new).
- **Gates:** SDK suite 407 passed; ruff + format clean; pyright 0; check_notebooks green.
- **Commits:** 76571ef1 (SDK synthesizer binding + per-shape fetches), 5940219c
  (2x2 notebook rebuild); pushed to upstream, draft PR #467 (base OME-718-ifeval).
  Follow-up: packages/screamingface/justfile — stack-up/down/status/logs/prepare +
  notebook-ifeval recipes so the notebook's three-terminal prerequisite is one command
  (pattern ported from the OME-605 worktree's local justfile; paths repo-rooted).
- **Deviations:** the old test_client_fetches_once... updated to assert the per-shape
  fetch contract (2 GETs for mixed shapes) — same owner-approved change set.

## Follow-up — provider-stable first run

### Intent

Make notebook 07 reliable as a first end-to-end validation without misrepresenting Khoa's
Kimi K3 experiment. A live canonical Evaluation showed that Kimi K3 can exhaust its entire
4,096-token completion budget or return an upstream provider error before producing a
scorable answer. The Engine correctly fails loudly in that situation.

### Planned changes

- `packages/screamingface/tests/test_ifeval_notebook.py` — pin the notebook's required smoke
  candidates and keep Kimi K3 in an explicitly optional provider-sensitive section
- `packages/screamingface/scripts/build_notebooks.py` — put a one-Case Haiku/Gemini smoke
  grid before the optional Kimi K3 research configuration; explain kernel restarts and loud
  Candidate/provider failures
- `packages/screamingface/examples/07_ifeval_e2e.ipynb` — regenerate from the maintained
  source; never hand-edit the artifact

### Test plan

RED first: the notebook contract test must fail while every required Evaluation still uses
Kimi K3. Then regenerate and run the focused test, `scripts/check_notebooks.py`, and the SDK
stack's complete repository gates.

### Acceptance

- A fresh researcher can validate canonical IFEval and both corrective Variants with
  `limit=1` using the stable smoke candidates
- Khoa's Kimi K3 configuration remains available and clearly labeled as optional research,
  not a reliable environment-health check
- Correct slash-qualified Benchmark ids remain visible; provider failures remain loud

### Outcome

- **Actual files:** `tests/test_ifeval_notebook.py` adds the Run-All contract;
  `scripts/build_notebooks.py` now generates a paid one-Case Haiku/Gemini smoke grid plus
  stale-kernel and fail-loud guidance; `scripts/_ifeval_notebook.py` owns the disabled Kimi
  K3 appendix so the main builder remains focused at 437 lines;
  `examples/07_ifeval_e2e.ipynb` was regenerated from that source.
- **RED:** `pytest tests/test_ifeval_notebook.py -q` failed 2 tests because the former
  notebook used `limit=3` and made Kimi K3 unconditional.
- **GREEN:** focused suite 2 passed; deterministic notebook check green; full SDK suite
  414 passed / 14 skipped at 95.00% coverage; Ruff lint and format green; Pyright 0;
  wheel + sdist built; distribution-content check green.
- **Live acceptance:** a fresh isolated kernel executed all 10 code cells with zero errors.
  Canonical Model, canonical Fusion, self-corrective Model, and verifying-ensemble Fusion
  each returned `Report(ok=True)` for one Case. Scores were 1.0; output-token totals were
  415, 1,283, 2,163, and 3,276 respectively. The Kimi appendix remained skipped. The
  executed proof is `/private/tmp/07_ifeval_e2e.provider-stable.executed.ipynb`.
- **Preservation:** the pre-regeneration notebook had no outputs or execution counts, only
  local kernel metadata; its exact bytes remain at
  `/private/tmp/07_ifeval_e2e.pre-provider-stable.ipynb`.
- **Commits:** this focused restack commit
  (`docs(screamingface): stabilize IFEval first run`); no push, PR, or Linear mutation.
- **Deviations:** the stack-routing gap found during this follow-up was resolved in the approved
  OME-605 cleanup without creating another issue. `run_gates.py screamingface` now routes the
  exact SDK lane and completed fully green.
