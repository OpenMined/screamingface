---
id: OME-400
linear_url: https://linear.app/openmined/issue/OME-400/sf-notebook-ship-00-quickstart-the-sdk-surface-it-needs
status: in_progress
type: feature
priority: P0
labels: [py-screamingface]
created: 2026-07-13
closed:
---

Ship `00_quickstart.ipynb` + the SDK surface it needs: new package `packages/screamingface`
(import + PyPI `screamingface`), scaffolded like `packages/url4`, porting the quickstart
slice of the `screamingface-contract` prototype (product-demos) — `sf.setup`,
`sf.models.list`, `sf.Fusion(reduce=, judge=)` with shareable flat `url4://` string,
`evaluate("gpqa", first=, seed=)`, `run.score/baseline/gain` — with the deterministic
`SimulatedBackend` behind a hexagonal `EngineBackend` port (real engine = OME-296 adapter
swap; real url4 grammar = OME-408). Mock/static widgets only (live widgets = OME-407).
Notebook executed with outputs committed; new `screamingface-tests.yml` CI lane.
Owner-verify: landing label `pkg/screamingface` creation + card registration.
Ledger: `docs/work/2026-07-13-OME-400-quickstart-sdk.md`.
