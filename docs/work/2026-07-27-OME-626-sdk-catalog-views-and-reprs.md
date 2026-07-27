---
ticket: OME-626
stack: screamingface
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-626 — SDK catalog views and widget-like reprs for Model/Fusion/Benchmark

## Intent

Give the notebook SDK a branded rich display for its core objects, matching the
`widgets-view` design mock. Today evaluating a `Model`, `Fusion`, or `Benchmark` in a cell
prints the bare frozen-dataclass `repr`, and there is no way to browse the engine catalog
visually. This unit adds:

- static `_repr_html_()` cards (plus a text `__repr__` fallback) on `Model`, `Fusion`, and
  `Benchmark`; and
- `sf.models.view()` / `sf.benchmarks.view()` interactive ipywidgets catalogs (search/filter),
  modeled on the existing `ConnectionPanel`, with a static `_repr_html_` fallback when
  ipywidgets is absent.

**Honesty constraint (owner-approved):** the engine advertises no price, context-window, or
ability-score data. The mock's price/context/ability bars have no backing data, so cards show
**only real advertised fields** — never fabricated numbers. This keeps the SDK's
"simulated but honest" stance intact.

## Planned changes

- New `src/screamingface/_card_display.py` — pure HTML functions
  (`model_card_html`, `fusion_card_html`, `benchmark_card_html`,
  `models_catalog_html`, `benchmarks_catalog_html`) + text repr helpers; card CSS appended to
  the shared `.sf-ui` token block from `_display.STYLE`.
- New `src/screamingface/_catalog_view.py` — `ModelsView` / `BenchmarksView` widget classes
  (`widget()`, `_repr_html_()`, `_ipython_display_()`), `.value` = filtered ids.
- Edit `model.py`, `fusion.py`, `benchmark.py` — add `_repr_html_` + `__repr__` (lazy import
  of `_card_display` to avoid cycles).
- Edit `models.py`, `benchmarks.py` — add `view(*, query=None, tools=())`; extract a shared
  `_filter_records` helper so `view()` and `list()` agree exactly.
- Edit `__init__.py` — export `ModelsView` / `BenchmarksView` if the value type needs to be
  importable.
- New tests under `tests/`.

## Test plan (RED first)

- `Model/Fusion/Benchmark._repr_html_` contain the real fields (id/route/provider/prompt/
  params/url4 for Model; name/reducer/members/model_ids/url4 for Fusion; id/title/grader/
  aggregator/tools/max_tool_calls for Benchmark) and contain **no** fabricated price/ability
  text; injected values are HTML-escaped (XSS), mirroring the connection-panel tests.
- `models.view()`/`benchmarks.view()` build from a mocked registry (`httpx.MockTransport`);
  `.value` equals the filtered ids; static fallback renders when ipywidgets is absent; the
  search box narrows rows when ipywidgets is present.
- `view()` and `list()` return the same ids for the same `query`/`tools` args (invariant).

## Acceptance

- Evaluating a `Model`, `Fusion`, or `Benchmark` in a notebook renders a branded card.
- `sf.models.view()` / `sf.benchmarks.view()` render a searchable catalog (static fallback
  without ipywidgets).
- No fabricated metrics anywhere in the output.
- Full `screamingface` gates green (ruff/format/pyright/pytest ≥95% cov, engine suite,
  contract fixtures, notebook check, build).

## Outcome

- **Actual files:** as planned. New `src/screamingface/_card_display.py` (card + catalog HTML
  renderers) and `src/screamingface/_catalog_view.py` (`ModelsView`/`BenchmarksView`).
  Added `_repr_html_` to `model.py`, `fusion.py`, `benchmark.py`. Added `view()` +
  `_filtered_models`/`_filtered_benchmarks` to `models.py`/`benchmarks.py` (shared with
  `list()`). New test module `tests/test_ome626_display.py` (13 tests). `__init__.py` was
  **not** changed — the view classes did not need top-level export.
- **Commit:** feat(screamingface): add catalog views and widget-like reprs (Refs: OME-626).
- **Gates:** `run_gates.py screamingface` → ALL GATES GREEN (append-only, ruff, format,
  pyright, SDK pytest ≥95%, engine pytest ≥95%, contract fixtures, notebook check, build).
  Full SDK suite 733 + 13 new = 746 passing.
- **Deviations:**
  - No custom `__repr__` added. The frozen-dataclass-generated `__repr__` already gives a
    concise text repr and satisfies the existing contract test
    (`test_phase1_values.py::test_fusion_repr_is_compact...` asserts a member route appears);
    a hand-written repr risked breaking that append-only test for no gain. `_repr_html_` is
    the notebook display hook, which is the actual requirement.
  - The full whole-tree gate initially failed on 7 pre-existing, unrelated modified example
    notebooks (OME-400 WIP already dirty at session start). Per owner decision these were
    `git stash`-ed to prove a fully green gate on the OME-626-only tree, the OME-626 files
    were committed alone, and the stash was restored — no unrelated change was committed or
    discarded.
