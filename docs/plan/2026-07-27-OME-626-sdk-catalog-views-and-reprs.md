---
title: SDK catalog views and widget-like reprs — implementation plan
ticket: OME-626
status: approved
date: 2026-07-27
spec: docs/spec/2026-07-27-OME-626-sdk-display-contract.md
---

# SDK catalog views and widget-like reprs — implementation plan

Implements `docs/spec/2026-07-27-OME-626-sdk-display-contract.md`. Follows the established
widget pattern in `_connection_panel.py` / `_progress.py`: inline-CSS HTML scoped under
`.sf-ui`, base tokens from `_display.STYLE`, `ipywidgets` optional with a static
`_repr_html_` fallback.

## Iterations (each a RED → GREEN → gate cycle)

1. **Card renderers** — `_card_display.py`: `model_card_html`, `fusion_card_html`,
   `benchmark_card_html`, and text repr helpers. Card CSS appended to the shared `.sf-ui`
   block (reuse `--sf-gain`/`--sf-line`/`--sf-ink*`; no raw colors). RED: HTML contains the
   real fields, escapes injected text, and contains no price/ability strings.
2. **Object reprs** — add `_repr_html_` + `__repr__` to `Model`, `Fusion`, `Benchmark`
   (lazy import of `_card_display`). RED: each type's display delegates to its renderer.
3. **Catalog renderers + views** — `models_catalog_html` / `benchmarks_catalog_html` in
   `_card_display.py`; `ModelsView` / `BenchmarksView` in `_catalog_view.py`
   (`widget()`, `_repr_html_`, `_ipython_display_`, `.value` = filtered ids). RED: static
   catalog HTML lists ids; `.value` matches; widget tree filters on search input.
4. **Entry points** — `models.view()` / `benchmarks.view()`; extract a shared
   `_filter_records` helper in each module so `view()` and `list()` agree. Export the view
   classes from `__init__.py` if the value type must be importable. RED: `view()` builds from
   a mocked registry; `view()` ids == `list()` ids for equal args.

## Critical files

- New: `src/screamingface/_card_display.py`, `src/screamingface/_catalog_view.py`
- Edit: `src/screamingface/{model,fusion,benchmark,models,benchmarks,__init__}.py`
- Reuse: `_display.STYLE`, `_profile.load_registry()` / `ModelRecord` / `BenchmarkRecord`,
  the `Recipe.url4` property, and the existing `list()` filter logic.
- Tests: new files under `packages/screamingface/tests/`.

## Verification

- `uv run .claude/scripts/run_gates.py screamingface` green from the repo root.
- Manual notebook smoke in `packages/screamingface/examples/`: render a `Model`, `Fusion`,
  and `Benchmark`; run `sf.models.view()` / `sf.benchmarks.view()`, type in the search box,
  confirm rows filter and `.value` updates; confirm the static render with ipywidgets absent.
