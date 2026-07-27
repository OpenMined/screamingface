---
id: OME-626
linear_url: https://linear.app/openmined/issue/OME-626
status: in_progress
type: feature
priority: 3
labels: [py-screamingface, agentic, autonomous]
created: 2026-07-27
closed:
---

Add `sf.models.view()` / `sf.benchmarks.view()` catalog browsers and widget-like
`_repr_html_` cards for `Model`, `Fusion`, and `Benchmark`, matching the `widgets-view`
design mock.

Honest-fields-only (owner decision): cards render only what the engine advertises — no
fabricated price/context/ability data. Static reprs for the three objects; interactive
ipywidgets catalogs for the two `.view()` entry points, with a static fallback when
ipywidgets is absent. `sf.mt(...)` and any engine change are out of scope.

- Spec: `docs/spec/2026-07-27-OME-626-sdk-display-contract.md`
- Plan: `docs/plan/2026-07-27-OME-626-sdk-catalog-views-and-reprs.md`
- Ledger: `docs/work/2026-07-27-OME-626-sdk-catalog-views-and-reprs.md`
