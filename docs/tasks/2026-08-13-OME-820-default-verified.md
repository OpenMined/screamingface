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

# Default new leaderboard submissions to verified as a placeholder

Action item from the 2026-08-13 dev huddle (`[52:20]`). `verified_by_openmined` defaults to `False`
and no route can ever set it, so with `OME-414` unstaffed the board reads "unverified" on every row
permanently.

The change is one character; the decision is what the flag then claims. **Revised 2026-08-14 after
review:** an earlier version of this ticket said verified means "this run executed on OpenMined
infrastructure". Nothing supports that — the SDK takes independent engine and scoreboard URLs, the
chart ships `authMode: disabled`, and `submit()` never sets the field, so a submission is an
unattested client payload. The claim is **withdrawn**: the default asserts **nothing**. It exists so
the board does not read "unverified" on every row while no verification exists. See spec §2.1a.

Client-settability stays forbidden, and existing rows are not backfilled.

**This default has an expiry condition.** It is honest only while every execution path is ours;
BYOK and local/packaged execution are self-reported. That is `OME-821`, filed and linked blocked-by.
Local packaging was reported at the same huddle as landing by EOD, so the window is days.

Spec: `docs/spec/2026-08-13-OME-820-default-verified.md`
Plan: `docs/plan/2026-08-13-OME-820-default-verified.md`
Ledger: `docs/work/2026-08-13-OME-820-default-verified.md`
Follow-up: `OME-821` — distinguish self-reported runs (blocked by this)
