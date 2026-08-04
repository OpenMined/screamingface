---
ticket: OME-732
stack: screamingface
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-732 — SDK: synthesizer binding + members-aware fetch + minimal notebook 07

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
