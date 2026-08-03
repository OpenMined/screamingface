---
ticket: OME-720
stack: repo
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-720 — Add IFEval e2e example notebook to the SDK

## Intent

Give researchers a zero-judge on-ramp: notebook 07 runs IFEval end-to-end with only an
OpenRouter key (one candidate call per prompt, free deterministic grading). Companion to
the engine-side family package (`OME-719`); parent epic `OME-718`.

## Planned changes

- `packages/screamingface/scripts/build_notebooks.py` — add `07_ifeval_e2e.ipynb` cell
  definitions mirroring `05_draco_e2e.ipynb` (connect → model → evaluate → report),
  with the ifeval prepare command (incl. nltk corpus note) and no-judge cost framing
- `packages/screamingface/examples/07_ifeval_e2e.ipynb` — generated artifact

## Test plan

- `scripts/check_notebooks.py` green (gates cell drift AND the example file set — the
  invariant that examples are generated, never hand-dropped)
- screamingface package CI gate set locally: ruff, format, pyright, pytest

## Acceptance

- Notebook 07 present + check green
- Live e2e (shared with OME-719 acceptance): `sf.evaluate(model, benchmark="ifeval",
  limit≈5)` against local gateway+engine returns `Report(ok=True)` with verifier scores

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned (`build_notebooks.py` + generated `07_ifeval_e2e.ipynb`).
- **Commits:** NONE by explicit owner instruction — dirty tree for manual review.
- **Gates:** `check_notebooks.py` green; SDK ruff/format/pyright green; pytest 351
  passed. ⚠️ SDK coverage gate 94.78% < 95 is PRE-EXISTING on the branch (this unit
  touched only scripts/ + generated examples, neither in `--cov=screamingface` scope)
  — flag to Keelan, not fixed here (surgical-changes rule).
- **E2E:** shared with OME-719 — live 5-case run green (see that ledger).
- **Deviations:** regenerating examples reset the pre-existing uncommitted execution
  outputs in `00_quickstart.ipynb` (cell sources identical — generator output; only
  outputs/exec state lost). Surfaced to owner in-session.
