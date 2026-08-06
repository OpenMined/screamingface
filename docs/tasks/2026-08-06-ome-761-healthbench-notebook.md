---
id: OME-761
linear_url: https://linear.app/openmined/issue/OME-761/add-the-healthbench-worst-30percent-e2e-notebook-spend-gated
status: backlog
type:
priority: P1
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-06
closed:
---

# OME-761 — Add the HealthBench worst-30% e2e notebook (spend-gated)

SDK half of `OME-759`: `packages/screamingface/examples/08_healthbench_worst30.ipynb`.
connect → smoke (pennies, only ungated cell) → gated (`RUN_EVALUATION = False`) worst30
attempt → report reading. Challenge framing + "not an official HealthBench score" label +
protocol caveats. Zero SDK src changes expected; paid execution is Khoa's, never
agentic. Blocked by `OME-760`.
