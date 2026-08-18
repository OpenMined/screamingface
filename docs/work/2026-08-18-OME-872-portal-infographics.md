---
ticket: OME-872
stack: scoreboard (portal static only; no python)
status: in_progress
started: 2026-08-18
finished:
---

# OME-872 — Render benchmark explainer infographics on the portal benchmark page

## Intent

The portal's per-benchmark page explains its benchmark in prose only; fractional and
negative scores read as bugs to visitors. Render the benchmark's sf-dark explainer
infographic (shared with OME-870) between the description and the READ THIS FIRST box —
data-driven by benchmark id, fail-silent when no asset exists.

## Planned changes

- `apps/scoreboard/portal/assets/benchmarks/{draco,ifeval,healthbench-worst30}.svg` —
  the three infographics, named by benchmark id.
- `portal/benchmark.html` — hidden `<img id="benchmark-infographic">` slot.
- `portal/style.css` — one `.infographic` rule (tokens only).
- `portal/benchmark.js` — set `src = assets/benchmarks/<id>.svg`; unhide on load only.

## Test plan

- Existing portal Node tests stay green (pure logic untouched).
- Live check: healthbench-worst30 page shows the infographic; a benchmark without an
  asset (e.g. a legacy id) renders exactly as before (slot stays hidden).

## Acceptance

- Infographic renders on draco/ifeval/healthbench-worst30 pages; absent elsewhere; no
  layout shift when absent; scoreboard gates green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned
- **Commits:** (pending owner review — uncommitted with the OME-870 batch)
- **Gates:** portal Node tests 19 pass; live screenshot verified on healthbench-worst30
- **Deviations:** none
