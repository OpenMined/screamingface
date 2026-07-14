---
ticket: OME-373
stack: scoreboard
status: done
started: 2026-07-13
finished: 2026-07-13
---

# OME-373 — Plausible analytics on the public scoreboard portal

## Intent

Irina asked for traffic/visit analytics on the leaderboard, to measure whether the
public claim is landing and whether externals are actually reaching the verified
board this week. Filip proposed reusing the existing OpenMined Plausible plan
(previously used for askanyone.ai) for `scoreboard.screamingface.ai` rather than
standing up a new analytics stack. Bennett (Branding & Marketing Lead, owns the
Plausible account) confirmed the domain was added to the plan and supplied the
tracking snippet over Slack DM on 2026-07-13. This unit wires that snippet into the
portal so it starts collecting data; Bennett verifies once it's live.

## Planned changes

- `apps/scoreboard/portal/index.html`, `benchmark.html`, `spec.html`, `data.html` —
  insert Bennett's Plausible `<script>` snippet (site id `pa-ysspwNldM0r_4o-m1utPa`)
  into `<head>`, before `</head>`, in all four pages (they share an identical head
  boilerplate today — fonts/icon/theme script are already duplicated per-page, so
  this follows the existing pattern rather than introducing a templating layer for
  one script tag).
- `apps/scoreboard/tests/unit/test_portal_static.py` — new test asserting each
  served HTML page includes the Plausible script tag, so a future portal-page
  rewrite can't silently drop analytics.

## Test plan

- RED: assert `GET /index.html`, `/benchmark.html`, `/spec.html`, `/data.html` each
  contain the Plausible script src (`plausible.io/js/pa-ysspwNldM0r_4o-m1utPa.js`) —
  fails against the current (unmodified) portal HTML.
- GREEN: insert the snippet into all four pages; same assertion passes.
- No backend/business logic changes — pure static-asset addition, no migration, no
  Tortoise-touching code (`tortoise-dev` companion skill's `when` doesn't match).

## Acceptance

- All four public portal pages serve the Plausible snippet in `<head>`.
- Existing portal tests (`test_portal_static.py`) remain green and unmodified.
- `run_gates.py scoreboard --skip-append-only` all green.
- Bennett notified once merged/deployed so he can verify traffic is flowing.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `apps/scoreboard/portal/index.html`, `benchmark.html`, `spec.html`, `data.html` —
    inserted Bennett's Plausible snippet into `<head>` (all four, exactly as planned).
  - `apps/scoreboard/tests/unit/test_portal_static.py` — new
    `test_portal_pages_include_plausible_analytics`, RED confirmed before the HTML
    edit, GREEN after.
- **Commits:** this unit's commit (`Refs: OME-373`).
- **Gates:** `run_gates.py scoreboard --skip-append-only` — ALL GATES GREEN (ruff
  check, ruff format --check, pyright, pytest). 114 passed, 1 skipped, 88.16%
  coverage.
- **Deviations:** none — matched the plan exactly.
