# OME-922 — Partial submission warning

Status: approved by owner, 2026-08-20 · Stack: screamingface

## Problem

`sf.evaluate(..., limit=N)` can produce a valid score with 100% coverage of the selected
Cases even though it covers only part of the Benchmark. Submitting that Candidate currently
looks identical to submitting a full run, but the public leaderboard ranks only full runs.

## Contract

- `sf.leaderboards.submit(candidate)` and its async equivalent emit this `UserWarning`
  before sending a partial but otherwise valid score:

  > Your submission is partial. The public leaderboard ranks only scores for full runs.

- A Candidate is full only when both conditions hold:
  - its Case count equals `candidate.benchmark.case_count`; and
  - its Engine-owned `coverage` is `1.0`.
- The warning does not block or modify the submitted payload.
- A full run emits no warning.
- Existing validation remains authoritative; an unscored Candidate is rejected rather than
  described as a successful submission.

## Non-goals

- Enforcing full-run ranking in `apps/scoreboard`.
- Changing report rendering or the public `CandidateResult` API.
- Introducing a custom warning class or warning-filter configuration.
