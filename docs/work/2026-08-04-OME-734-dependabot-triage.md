---
ticket: OME-734
stack: repo
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-734 — merge the green Dependabot PRs and clear the subsumed pair

## Intent

16 of the 30 open PRs are Dependabot's, some three weeks stale, against 100 open security
alerts. This unit triages all 16 and merges every PR that is green, driving the alert count
down before any structural work starts. No code changes — merges only.

The unit exists because the naive reading of the backlog ("close whatever a higher bump
supersedes") is wrong here, and the reasoning needs to be on the record.

## The overlap finding

Computed over every (directory, package) pair across all 16 PRs. Only two collisions exist:

| Subsumed | Superseded by | Directory | CI |
|---|---|---|---|
| #433 cryptography →48.0.1 | #436 →49.0.0 | `/apps/aigateway` | #433 green · #436 red |
| #455 next →16.2.11 | #457 →16.2.12 | `/apps/aigateway-ui` | #455 green · #457 red |

Verified `49.0.0 >= 48.0.1` and `16.2.12 >= 16.2.11` by parsed version comparison, not by eye.

Two pairs that look like duplicates are not: `starlette` #431 (`/apps/aigateway`) vs #430
(`/apps/scoreboard`), and `next` #455 (`/apps/aigateway-ui`) vs #422
(`/apps/screamingface-studio/frontend`) — different directories. Neither group PR (#436,
#397) contains `starlette` at all, so #431/#430 stand on their own.

## The decision: merge the subsumed pair, do not close it

Closing a Dependabot PR suppresses recreation for that version. Both subsumed PRs are the
**only green fix** for a high-severity alert, and both are superseded by PRs that are **red**.
Closing them would leave two high alerts with no open fix for as long as the group PRs stay
broken.

Merging achieves the same end state without that window: Dependabot rebases #436 onto
`48.0.1 → 49.0.0` and #457 onto `16.2.11 → 16.2.12` and drops the redundant entries itself.

## Planned changes

- `docs/work/2026-08-04-OME-734-dependabot-triage.md` (this file)
- `docs/tasks/2026-08-04-ome-734-dependabot-triage.md`

No source file is touched by this unit. The PR merges happen on GitHub.

## Test plan

No tests are authored here — this unit merges other people's (Dependabot's) verified changes.
The gate is each PR's own CI, re-verified immediately before its merge rather than trusted from
the 2026-08-04 survey, since PRs rebase and checks expire.

## Acceptance

- Every green Dependabot PR merged; none closed (#439 is closed under OME-740, not here).
- The overlap matrix re-runs with **zero** collisions.
- #436 and #457 show rebased onto the new bases rather than left stale.
- Alert count captured before and after, so later phases have a baseline.

## Outcome

- **Actual files:** as planned — this ledger and its `docs/tasks/` mirror. No source file touched.

- **Result: 17 Dependabot PRs merged, open alerts 100 → 51.**

  | Manifest | Before | After |
  |---|---:|---:|
  | `apps/server/uv.lock` | 35 | 38 |
  | `apps/aigateway/uv.lock` | 22 | 7 |
  | `apps/screamingface-studio/frontend/package-lock.json` | 15 | 0 |
  | `apps/aigateway-ui/package-lock.json` | 13 | 0 |
  | `apps/scoreboard/uv.lock` | 6 | 0 |
  | `apps/aigateway/pyproject.toml` | 6 | 5 |
  | `public-docs/package-lock.json` | 2 | 0 |
  | `apps/screamingface-studio/src-tauri/Cargo.lock` | 1 | 1 |
  | **total** | **100** | **51** |

  Four trees went fully clean. Of the 51 remaining, **38 are the stale `apps/server` tree** —
  only **13** are real.

- **Merged:** #397 #430 #431 #432 #433 #437 #453 #454 #455 #456 #460 #468 #469 #470 #471 #473 #474

- **Gates:** every merge gated on `mergeStateStatus == CLEAN` re-read immediately beforehand,
  never on the 2026-08-04 survey. Nothing forced; no `--admin`. Merges were serialised one per
  manifest, because GitHub resets every open PR's mergeability to `UNKNOWN` after each merge and
  a naive batch silently skips the rest. Helper: `scratchpad/merge_clean.py` (poll-until-terminal,
  merge only on `CLEAN`).

- **Deviations from plan — three, all upward:**

  1. **The plan listed 13 merges; 17 landed.** Merging is not a static set: each merge made
     Dependabot re-evaluate and open *better* PRs, which were then merged in turn. #469
     (cryptography →**50.0.0**) superseded the #436 group's →49.0.0 entry within minutes of #433
     landing, and #473/#474 appeared and were merged after #455.

  2. **The subsumed pair resolved exactly as predicted, and so did a third case.** #422 and #435
     were closed *by Dependabot* as superseded (#470, #471) rather than by us, and #457 closed
     itself once #472 replaced it — direct confirmation that merging rather than closing is what
     lets the bot converge on its own.

  3. **`apps/server` alerts rose 35 → 38 while its tree stayed deleted.** Alerts are still being
     generated against a manifest removed in `9a9cf82d`. This strengthens the case for the
     dismissal sub-issue rather than weakening it.

- **Left open, each owned by a sibling sub-issue:**
  - **#436** aigateway group — red on `pyright` → `OME-735`
  - **#472** aigateway-ui group (replaced #457, now 15 updates) — red on `npm ci` → `OME-736`
  - **#439** url4-cloud Docker — broken two-stage bump → `OME-740`

- **Residual real alerts (13):** `pyjwt` needs ≥2.13.0 (7 rows, `OME-735`), `idna` ≥3.15 and
  `pydantic-settings` ≥2.14.2 in `apps/aigateway/uv.lock` (both covered by #436 → `OME-735`),
  and `glib` ≥0.20.0 in `src-tauri/Cargo.lock` — which has **no configured ecosystem at all**,
  so it can only be fixed under `OME-737`.
