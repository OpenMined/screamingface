---
ticket: OME-761
stack: url4-cloud
status: in_progress
started: 2026-08-06
finished:
---

# OME-761 — Add the HealthBench worst-30% e2e notebook (spend-gated)

## Intent

One generated notebook (`packages/screamingface/examples/08_healthbench_worst30.ipynb`)
walking connect → smoke (pennies, the only ungated paid cell) → spend-gated worst30
challenge attempt with an open-weights Fusion → reading the Report. Carries the
challenge framing, the "not an official HealthBench score" label, and the protocol
caveats. Epic `OME-759`; design `.dk/plans/2026-08-05-healthbench-sf.md` §4.7.

## Planned changes

- `packages/screamingface/scripts/build_notebooks.py` — add
  `_healthbench_worst30_e2e()` + registry entry
- `packages/screamingface/examples/08_healthbench_worst30.ipynb` — generated output

## Test plan

- `uv run python scripts/build_notebooks.py` regenerates deterministically
- `uv run python scripts/check_notebooks.py` green (existing notebook gate)
- Grep-level assertion: `sf.evaluate(...)` on `healthbench/worst30` appears ONLY under
  `RUN_EVALUATION` (B4 rule); the smoke cell is the only ungated paid call.

## Acceptance

- Notebook builds + passes the repo's notebook checks; zero SDK src changes.
- Paid execution left to Khoa (gates ship OFF; outputs empty).

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned (`build_notebooks.py` + generated
  `08_healthbench_worst30.ipynb`); zero SDK src changes.
- **Gates:** `build_notebooks.py` regenerates deterministically ✓ ·
  `check_notebooks.py` exit 0 ✓ · SDK pytest 530 passed / 14 skipped ✓ · ruff + pyright
  on scripts: clean ✓ · B4 audit: the only ungated `sf.evaluate` is `healthbench/smoke`
  (2 paid calls); the worst30 run sits under `RUN_EVALUATION = False`.
- **Commits:** none yet — awaiting Khoa's local review
- **Gates:**
- **Deviations:** open trio uses `qwen3.6-plus` in place of July's GLM-5.2 — GLM has no
  declared route in the Engine's url4.toml; the engine-rerun target (OME-762) keeps the
  comparison internally consistent.
