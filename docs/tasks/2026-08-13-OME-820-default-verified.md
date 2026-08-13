---
id: OME-820
linear_url: https://linear.app/openmined/issue/OME-820/default-new-leaderboard-submissions-to-verified-ran-on-openmined
status: In Progress
type: Feature
priority: P1
labels: [scoreboard, agentic, autonomous]
created: 2026-08-13
closed:
---

# Default new leaderboard submissions to verified (ran on OpenMined infrastructure)

Action item from the 2026-08-13 dev huddle (`[52:20]`). `verified_by_openmined` defaults to `False`
and no route can ever set it, so with `OME-414` unstaffed the board reads "unverified" on every row
permanently.

The change is one character; the decision is what the flag then claims. Owner decision: **verified
means "this run executed on OpenMined infrastructure"** — true for the Monday cohort, who run on the
hosted engine through OpenMined's gateway and capped keys. Flipping the default while keeping the
old "we reproduced this" meaning was rejected as publishing a reproduction that never happened.

Client-settability stays forbidden, and existing rows are not backfilled.

**This default has an expiry condition.** It is honest only while every execution path is ours;
BYOK and local/packaged execution are self-reported. That is `OME-821`, filed and linked blocked-by.
Local packaging was reported at the same huddle as landing by EOD, so the window is days.

Spec: `docs/spec/2026-08-13-OME-820-default-verified.md`
Plan: `docs/plan/2026-08-13-OME-820-default-verified.md`
Ledger: `docs/work/2026-08-13-OME-820-default-verified.md`
Follow-up: `OME-821` — distinguish self-reported runs (blocked by this)
