---
id: OME-323
linear_url: https://linear.app/openmined/issue/OME-323/ome-323-open-vs-closed-frontier-statistics-main-page-screamingfaceai
status: in_progress
type: task
priority: P1
labels: [scoreboard, autonomous, agentic]
created: 2026-07-17
closed:
---

Open vs. closed frontier statistics — show how much of the accuracy frontier is
held by open, reproducible stacks vs. proprietary ones, backed by real
`Score`/`Baseline` rows, not mock data.

Spec drafted 2026-07-16 (`docs/spec/2026-07-16-open-vs-closed-frontier-stats-spec.md`),
left with one open decision (§4 classification approach). Resolved 2026-07-17
against a concrete precedent: Irina Bejan's 2026-07-17 comment on OME-428
confirms the org's real open/closed split — HuggingFace-routed models are
open-weight, OpenRouter/direct commercial-API models are closed. Spec updated
to Option A (provider/model registry) seeded from that split, fail-closed by
default. §6 ("what is the frontier") resolved to trend-over-time, matching the
ticket's own "frontier share + trend" scope line — not just a point-in-time
split.

Next: `docs/plan/` artifact, then implementation.
