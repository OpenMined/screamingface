---
ticket: OME-870
stack: screamingface (notebook content + assets; no runtime code)
status: in_progress
started: 2026-08-18
finished:
---

# OME-870 — Benchmark explainer infographics in the example notebooks

## Intent

Each benchmark notebook (06 DRACO, 07 IFEval, 08 HealthBench worst-30) explains its
benchmark in prose only; scoring mechanics (weighted rubrics, negative HealthBench
scores) surface only after a paid run. One succinct sf-dark infographic per notebook
shows dataset → candidate invocation → grading → score formula (with range) at a
glance, before any credits are spent. Style matches the existing sf-dark protocol-grid
reference (`.dk` preset).

## Planned changes

- `packages/screamingface/examples/assets/` — 3 new SVG (+PNG) infographics, drawio
  sf-dark: `draco-benchmark.svg/png`, `ifeval-benchmark.svg/png`,
  `healthbench-worst30-benchmark.svg/png` (+ the `.drawio` sources under
  `docs/diagrams/`).
- `packages/screamingface/scripts/build_notebooks.py` — markdown image cell near the
  top of each benchmark notebook referencing `assets/<name>.svg`.
- Regenerated example notebooks.

## Test plan

- Deterministic-notebook gate (`check_notebooks.py`) stays green after regeneration.
- Facts on each infographic verified against the Engine's own scorers
  (`_ifeval_score`, `_draco_score` + `draco/scoring.py`, `_healthbench_score` +
  `healthbench/scoring.py`) — the picture must not contradict the code.
- Image renders in JupyterLab from the relative `assets/` path.

## Acceptance

- Each of 06/07/08 opens with one glanceable, brand-styled infographic that names the
  dataset size, the grading mechanism (deterministic vs paid judge), the score formula
  and its range (incl. "negative is normal" for HealthBench worst-30).
- All screamingface gates green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus PNG renders alongside the SVGs. The `.drawio`
  sources planned for `docs/diagrams/` do not exist — the reference style is a
  hand-authored SVG, so the SVGs themselves are the sources.
- **Commits:** one commit on `OME-866-benchmark-native-scores` (shared PR #626).
- **Gates:** `run_gates.py screamingface` ALL GREEN (deterministic notebooks included);
  facts cross-checked against the Engine scorers; renders visually verified via
  headless browser.
- **Deviations:** hand-authored SVG instead of drawio (matches the actual reference
  artifact); infographics ride the OME-866 PR at owner request instead of their own.
