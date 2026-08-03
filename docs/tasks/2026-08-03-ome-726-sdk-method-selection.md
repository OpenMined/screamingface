---
ticket: OME-726
linear_url: https://linear.app/openmined/issue/OME-726/expose-benchmark-method-selection-in-the-sdk
status: todo
type: feature
priority: P1
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-03
closed:
---

# Expose benchmark method selection in the SDK

`sf.evaluate(..., benchmark="ifeval", method="single_pass")` +
`sf.benchmarks.get("ifeval", method=...)`; `method=None` = engine default
(corrective). Catalog display explains the methods; notebook 07 reworked around the
corrective default. Blocked by `OME-725`. Parent epic `OME-718`.
