---
id: OME-770
linear_url: https://linear.app/openmined/issue/OME-770/leaderboard-cost-and-pareto-cost-column-frontier-winner-marks-cost-vs
status: In Progress
type: Feature
priority: P2
labels: [scoreboard]
created: 2026-08-11
closed:
---

# Leaderboard: cost & Pareto — Cost column + frontier winner marks + cost-vs-accuracy chart

Filed by Irina Bejan, assigned to Filip Boltuzic, milestone
_🏆 Week 3 · Subsidized compute, $0 Colab & a verified board_.

**Split into two passes.** The ticket's scope — Cost column, Pareto frontier marks, cost-vs-accuracy
chart, cheapest-run stat — is entirely rendering, and none of it is buildable because no cost value
reaches Scoreboard at all.

- **Pass 1 (this unit, done 2026-08-13):** the half Scoreboard owns — a typed, nullable
  `run_cost_usd` accepted on submission, persisted, and exposed on both read paths. Backend only.
- **Pass 2 (still blocked):** the rendering. Blocked on two independent things — the frontier maths
  belongs in `portal/leaderboard-logic.js`, which lands with PR #569 (`OME-769`), and no client
  emits a run total yet (aigateway `OME-303` unmerged, no Engine roll-up, no Client field). Nobody
  is named for that chain; it is the open question on `OME-772`.

Ticket status stays **In Progress** — pass 1 closing does not satisfy the ticket's own
"Done when", which is about the column, the marks and the chart agreeing.

Spec: `docs/spec/2026-08-12-OME-770-run-cost-field.md`
Plan: `docs/plan/2026-08-12-OME-770-run-cost-field.md`
Ledger: `docs/work/2026-08-12-OME-770-run-cost-field.md`

## Label gap (owner action)

Linear carries only `scoreboard`. The repo's `task-management` rules require **one `actor`**
(`agentic`|`human`, mandatory) and **one `who-acts`** on SDLC items; both are absent. Agents never
mint or reassign label sets unprompted — `save_issue.labels` replaces the whole set — so this is
flagged rather than silently changed.
