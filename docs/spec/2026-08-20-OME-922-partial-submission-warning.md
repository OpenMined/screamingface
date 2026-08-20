# OME-922 — Partial submission warning

Status: approved by owner, 2026-08-20 · Stack: screamingface

## Problem

`sf.evaluate(..., limit=N)` can produce a valid score with 100% coverage of the selected
Cases even though it covers only part of the Benchmark. Submitting that Candidate currently
looks identical to submitting a full run, but the public leaderboard ranks only full runs.

## Contract

- `sf.leaderboards.submit(candidate)` and its async equivalent surface this message after
  successfully publishing a partial but otherwise valid score:

  > Your submission is partial. The public leaderboard ranks only scores for full runs.

- A Candidate is full only when both conditions hold:
  - its Case count equals `candidate.benchmark.case_count`; and
  - its Engine-owned `coverage` is `1.0`.
- In notebooks, the published score card carries a branded, non-error-looking
  `Partial submission` notice. It does not also emit a Python warning.
- Outside notebooks, the Client emits the message as a `UserWarning` so scripts and logs do
  not lose the advisory.
- The notice does not block or modify the submitted payload.
- A full run emits no warning.
- Existing validation remains authoritative; an unscored Candidate is rejected rather than
  described as a successful submission.

## Non-goals

- Enforcing full-run ranking in `apps/scoreboard`.
- Changing report rendering or the public `CandidateResult` API.
- Introducing a custom warning class or warning-filter configuration.

## Presentation

- Follow the canonical `OpenMined/screamingface-brand` status recipe at commit `7ea35a1`:
  persimmon warning semantics, a solid status square, square edges, no shadow, and no
  decorative gradient.
- Use the canonical light and dark warning tokens rather than the SDK's older amber aliases.
- Keep `Score published` and the success receipt: the partial score was persisted; the
  adjacent notice explains that it is not eligible for public ranking.
