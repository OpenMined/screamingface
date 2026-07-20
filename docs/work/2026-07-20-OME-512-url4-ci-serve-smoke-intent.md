---
ticket: OME-512
stack: url4
status: done   # planned | in_progress | done | blocked
started: 2026-07-20
finished: 2026-07-20
---

# OME-512 — url4 CI: fix serve-smoke expression illegal under OME-508

## Intent

The `serve smoke (url4[server])` CI job has been red on every commit since OME-508
(mandatory intent on groups). Its first assertion evaluates
`(/upper(hello world)!'go')` — an intent-less outer group, now HTTP 500
`missing_intent`. Fix the one stale expression so the job goes green. Not caused
by the recent main merge; the merge only surfaced the long-standing failure.

## Planned changes

- `.github/workflows/url4-tests.yml` — in the `Serve over real HTTP` step, change
  `(/upper(hello world)!'go')` → `(/upper(hello world)!'go')!''` (add the outer
  `!''` every sibling assertion already uses).

## Test plan

- Reproduced the 500 locally against `url4 serve` with the exact CI `url4.toml`.
- After the fix, run the FULL smoke script locally (complete config incl. the
  `science` shelf + `emily` identity) — all assertions pass, node returns 200s,
  error contract (400/404/405) intact.

## Acceptance

- `serve smoke (url4[server])` green on PR #402.
- Workflow-only; no engine/behaviour change; url4 gates still green.

## Outcome

- **Actual files:** `.github/workflows/url4-tests.yml` — 2 lines.
- **What:** the local full-script repro found **two** intent-less groups, not one.
  Both fixed with the outer `!''` every sibling assertion already uses:
  - `(/upper(hello world)!'go')` → `(/upper(hello world)!'go')!''` (the 500).
  - `(/nope(x)!'go')` → `(/nope(x)!'go')!''` (the 404-error-contract check, which
    would otherwise have 500'd and failed the step after the first fix).
- **Verification:** ran the FULL serve smoke script locally against `url4 serve`
  with the exact CI `url4.toml` (incl. `science` shelf + `emily` identity) under
  `set -euo pipefail` — exit 0, "serve smoke OK"; all evals 200, error contract
  400/404/405 intact. Workflow YAML re-validated.
- **Commits:** <sha — filled at commit>
- **Gates:** workflow-only change; no `packages/url4/src` or `tests` touched, so the
  url4 stack gates are unaffected (green as of merge commit a817bc4).
- **Deviations:** two expressions fixed rather than the one planned — the second
  surfaced only by running the complete script end-to-end, not just assertion #1.
