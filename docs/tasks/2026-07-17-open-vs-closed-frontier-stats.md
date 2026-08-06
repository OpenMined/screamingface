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

Extended 2026-08-06: nine follow-up dilemmas found while reviewing the spec against
real production data (mixed-provider classification, registry staleness, cross-system
drift, tie-breaking, baseline timing, frontier scope, junk production data,
unverified/anonymous submissions, manual override) — all resolved, folded into the
spec as new/extended §4, §6, §7, §8, plus new §9 (manual override column + migration)
and §10 (pre-launch production cleanup).

Next: `docs/plan/` artifact (existing draft at
`docs/plan/2026-08-06-open-vs-closed-frontier-stats-plan.md` needs updating against
these nine resolutions before implementation), then implementation. §10's production
cleanup is a separate, explicitly-confirmed action, not part of the code unit.
