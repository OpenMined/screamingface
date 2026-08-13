---
id: OME-808
linear_url: https://linear.app/openmined/issue/OME-808/add-repr-and-notebook-card-for-modelinfo-and-modeldetails-discovery
asana_url:
status: in_progress
type: task
priority: 3
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-13
closed:
---

# OME-808 — repr + notebook card for ModelInfo and ModelDetails

Add compact constructor-style `__repr__` to `ModelInfo` and `ModelDetails`, plus an SFDS
`_repr_html_` notebook card on `ModelDetails` only (mirrors the `Benchmark`/`BenchmarkInfo`
split). Discovery values currently fall back to the dataclass default repr, which for
`ModelDetails` dumps its entire nested contract.

Ledger: `docs/work/2026-08-13-OME-808-model-details-repr.md`
