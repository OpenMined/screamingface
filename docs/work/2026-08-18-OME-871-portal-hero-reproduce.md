---
ticket: OME-871
stack: scoreboard
status: done
started: 2026-08-18
finished: 2026-08-18
---

# OME-871 — Reword scoreboard portal hero to "Results you can reproduce, not just read."

## Intent

One-word copy change on the public Leaderboard portal landing page: the hero headline
says "rerun", which undersells the claim — reproducing a result is the scientific
promise; rerunning is just the mechanism. Requested by Khoa from a visual review.

## Planned changes

- `apps/scoreboard/portal/index.html` — `<h1>` "rerun" → "reproduce". Nothing else;
  the remaining "rerun" occurrences (hero paragraph, meta descriptions,
  `benchmark.html`/`spec.html`) correctly describe the action and stay.

## Test plan

- No behaviour change — static copy only. No test asserts the hero string
  (verified: `tests/portal/leaderboard-logic.test.js` covers pure logic only).
  Gate = scoreboard suite stays green.

## Acceptance

- Portal hero renders "Results you can reproduce, not just read."
- No other copy or logic changes in the diff.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** `apps/scoreboard/portal/index.html` (h1 only) +
  `tests/unit/test_portal_static.py` (hero-string assertion updated to the new copy —
  missed in the plan; the node portal tests were checked but not the pytest static
  suite) + this ledger + `docs/tasks/2026-08-18-portal-hero-reproduce.md`
- **Commits:** see PR (single commit, `Refs: OME-871`)
- **Gates:** `node --test tests/portal/leaderboard-logic.test.js` — fail 0; copy-only
  change, Python untouched (scoreboard CI lane runs on the PR)
- **Deviations:** none
