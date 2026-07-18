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
