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

**Umbrella for the notebook rich-display work — consolidates OME-628 / 630 / 635 / 637 / 639
(marked duplicates of this in Linear, 2026-07-27).** Their `docs/work` ledgers remain the
per-increment audit record.

Add `sf.models.view()` / `sf.benchmarks.view()` catalog browsers and widget-like
`_repr_html_` cards for `Model`, `Fusion`, `Benchmark`, plus `Connection`, `Case`, `Rubric`;
the full-form collapsible url4 recipe view; and the report-style benchmark card. Honest
advertised/authoring fields only — no fabricated price/context/ability. `sf.mt(...)` and any
engine change are out of scope.

Delivered on branch chain OME-626 → 628 → 630 → 635 → 637 → 639
(commits `782d634a`, `ea724ef9`, `2496cf74`, `21e59671`, `36366123`, `26b4c8e3`,
`0f2bccff`, `90535afb`, `9c7a40a4`); ~763 tests green; awaiting one PR to `main`.

- Spec: `docs/spec/2026-07-27-OME-626-sdk-display-contract.md`
- Plan: `docs/plan/2026-07-27-OME-626-sdk-catalog-views-and-reprs.md`
- Ledger: `docs/work/2026-07-27-OME-626-sdk-catalog-views-and-reprs.md`
