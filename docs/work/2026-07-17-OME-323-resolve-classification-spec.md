---
ticket: OME-323
stack: scoreboard
status: done
started: 2026-07-17
finished: 2026-07-17
---

# OME-323 — resolve open-vs-closed classification spec decision

## Intent

`docs/spec/2026-07-16-open-vs-closed-frontier-stats-spec.md` was left in draft with
one hard-blocking open question (§4: how to classify a `Score`/`Baseline` entry as
"open" vs. "closed") and one soft open question (§6: what "the frontier" means —
point-in-time split vs. trend). Both now have real evidence to resolve against
instead of guessing:

- §4: Irina Bejan's 2026-07-17 comment thread on OME-428 (OpenRouter support in the
  AI Gateway) states the org's actual policy: HuggingFace-routed models are
  open-weight, OpenRouter/direct commercial-API models are closed. This mirrors the
  same OR-vs-HF provenance split already used for cost routing in the (separate,
  not-in-this-repo) `screamingface-benchmarks` repo, per the 2026-07-13 benchmarking
  deck (slide 38).
- §6: OME-323's own ticket description says "Compute the frontier share **+ trend**
  from real board data" — this settles the sub-question in favor of trend-over-time,
  not a single top-1 snapshot, which the original spec draft had flagged as
  ambiguous.

This unit updates the spec document only — resolves §4 and §6, moves status out of
draft, and sets up the next `docs/plan/` artifact. No code in this unit.

## Planned changes

- `docs/spec/2026-07-16-open-vs-closed-frontier-stats-spec.md`: resolve §4 (lock to
  Option A, seeded from the OME-428 precedent), resolve §6 (trend-over-time), update
  frontmatter status, note the owner sign-off already obtained (per conversation with
  Filip, referencing Irina's OME-428 comment as sufficient confirmation).
- `docs/tasks/2026-07-17-open-vs-closed-frontier-stats.md`: mirror created (this
  ticket had none before).

## Test plan

N/A — spec-only artifact, no code path. Acceptance is the spec document itself:
no more open decisions blocking a `docs/plan/` write-up.

## Acceptance

- Spec's §4 and §6 no longer read "pending owner decision."
- Frontmatter `status` reflects the resolved state.
- Ticket mirror exists in `docs/tasks/`.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `docs/spec/2026-07-16-open-vs-closed-frontier-stats-spec.md` — §4 resolved
    (Option A, seeded from the OME-428 HF-vs-OpenRouter precedent, fail-closed
    default, drift risk flagged), §6 resolved (trend-over-time, per the ticket's own
    "frontier share + trend" text), §5/§8/frontmatter updated to match, original
    candidate-options text kept under a collapsed `<details>` for record.
  - `docs/tasks/2026-07-17-open-vs-closed-frontier-stats.md` — new mirror (none
    existed for OME-323 before this unit).
  - `docs/work/2026-07-17-OME-323-resolve-classification-spec.md` — this ledger.
- **Commits:** none yet — pending user's go-ahead to commit.
- **Gates:** N/A (no code path touched).
- **Deviations:** none. Owner sign-off obtained conversationally (Filip confirmed
  the OME-428 precedent is sufficient; no separate OME-323 Linear comment thread
  was required), logged via an OME-323 Linear comment instead of an approval loop.

## Round 2 (2026-08-06) — nine follow-up dilemmas surfaced and resolved

Before starting the `docs/plan/` implementation this spec sets up, a deeper pass
looked for problems the resolved §4/§6 decisions hadn't actually covered — informed
by real production data pulled directly from `https://scoreboard.screamingface.ai`
(the live leaderboard), not just the spec text in isolation. Nine distinct dilemmas
surfaced, each walked through and resolved with Filip one at a time:

1. **Mixed-provider fusion classification** — never actually specified; resolved
   closed-if-any-provider-is-closed.
2. **Registry staleness** — the fail-closed default silently undercounts "open" as
   new models ship; resolved to log/surface unrecognized entries instead of staying
   silent.
3. **Cross-system drift vs. AI Gateway's future classification** — resolved to ship
   now and cross-link the dependency directly in OME-428/OME-394, not just here.
4. **Tie-breaking on the frontier trend** — undefined, and already live: the real
   leaderboard has two submissions tied at 100% accuracy right now. Resolved:
   earliest holder keeps the position on a tie.
5. **Baseline `imported_at` vs. real-world chronology** — resolved: baselines count
   in the current split, excluded from the time-series trend.
6. **Per-spec vs. per-benchmark frontier scope** — resolved: benchmark-wide, per the
   spec's literal wording; gaming risk accepted as a non-goal.
7. **Junk data already in production** — the `DEPLOYMENT.md` smoke-test row
   (`score-007-smoke`) is live on production right now, confirmed by direct query.
   Resolved: manual one-time cleanup before this feature's first real computation.
8. **Unverified/anonymous submissions feeding a public claim** — resolved: ship
   as-is, consistent with how the rest of the leaderboard already works.
9. **No manual correction mechanism** — resolved: add an `openness_override` column
   to `Score` and `Baseline`, the one place this spec now requires a migration.

## Outcome — Round 2 (fill at the end — required before COMMIT)

- **Actual files:** `docs/spec/2026-07-16-open-vs-closed-frontier-stats-spec.md` —
  §4 extended (mixed-provider rule, staleness logging, cross-system drift resolved
  from "flagged" to "ship now + cross-link"), §6 extended (tie-breaking, baseline
  timing, frontier scope), §7 non-goals reconciled (migration language corrected,
  verification risk added as an explicit non-goal), §8 acceptance criteria extended,
  new §9 (manual override column + migration) and §10 (pre-launch production
  cleanup) added. `docs/work/2026-07-17-OME-323-resolve-classification-spec.md` —
  this round.
- **Commits:** pending — landing together with this round's changes.
- **Gates:** N/A (spec-only artifact, no code path).
- **Deviations:** none.
- **Owner-verify:** §10's production cleanup is a direct write against shared,
  live production data — must be executed as its own explicitly-confirmed action,
  separate from this spec commit, before the OME-323 implementation unit computes
  its first real number.
