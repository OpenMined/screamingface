---
ticket: OME-724
linear_url: https://linear.app/openmined/issue/OME-724/rich-benchmark-catalog-and-case-browsing-in-the-sdk-researcher
status: todo
type: feature
priority: P2
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-03
closed:
---

# Rich benchmark catalog and case browsing in the SDK + researcher notebook flow

`sf.benchmarks.list()` → rich `Benchmark` catalog (id, title, description, case_count)
with interactive cards; `Benchmark.cases(limit=, offset=)` prompt browsing via the
`OME-723` endpoint; `sf.benchmarks.get("ifeval")` pick step; `07_ifeval_e2e.ipynb`
(through `build_notebooks.py`) opens with list → pick → browse → evaluate. Blocked by
`OME-723`. Parent: `OME-722`.
