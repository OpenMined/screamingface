---
ticket: OME-728
stack: repo
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-728 — Add the CorrectiveEnsemble recipe to the SDK

## Intent

The Skurikhin et al. verifying ensemble as a public candidate recipe, run against
the frozen single_pass exam.

## Outcome

- **Actual files:** `corrective.py` (recipe), compiler template in
  `_evaluation/candidate.py` (per-case 3 members x 3 attempts, per-member
  check+feedback, judge tie-break, deterministic select/finalize; kind
  "corrective"), actions decode in `_evaluation/benchmark.py`, kind literals in
  model.py/report.py (incl. report._kind — found by the live run), public export,
  `tests/test_corrective_ensemble.py`, notebook 07 duel section.
- **Commits:** `2a3be1fd` feat: add SDK method selection and the CorrectiveEnsemble recipe (pushed to upstream/OME-605-screamingface-client-v1).
- **Gates:** SDK 387 green, notebook checks green, ruff/pyright green.
- **Deviations:** (1) `_action_payload` (bare struct render) — the named-src struct
  wrapper resolves for model calls but reaches plain endpoints EMPTY (found by
  in-process ensemble debug); (2) three separate kind validators existed
  (candidate/model/report) — report's was found only by the live run; (3) prior-test
  updates: public-surface set + OME-724 delegation stub track the grown interface.
- **Live:** interrupted at the final duel confirmation by owner (running notebook
  07 themselves); execution path fully proven in-process + live up to the report
  validator that was then fixed.
