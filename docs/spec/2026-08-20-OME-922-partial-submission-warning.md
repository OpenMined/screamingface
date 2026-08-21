# OME-922 — Partial submission warning

Status: approved by owner, 2026-08-20 · Stack: screamingface

## Problem

`sf.evaluate(..., limit=N)` can produce a valid score with 100% coverage of the selected
Cases even though it covers only part of the Benchmark. Submitting that Candidate currently
looks identical to submitting a full run. The public leaderboard currently accepts and ranks
partial submissions, but their scores cover fewer Cases and are not directly comparable with
scores from full runs.

## Contract

- `sf.leaderboards.submit(candidate)` and its async equivalent surface this message after
  successfully publishing a partial but otherwise valid score:

  > Partial submission. This score may appear on the public leaderboard, but it is based on
  > fewer benchmark cases and is not directly comparable with a full-run score.

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
- Changing Report structure, content, or the public `CandidateResult` API. The shared warning
  palette migration below is an intentional brand-token correction, not a new Report feature.
- Introducing a custom warning class or warning-filter configuration.

## Presentation

- Follow the canonical `OpenMined/screamingface-brand` status recipe at commit `7ea35a1`:
  persimmon warning semantics, a solid status square, square edges, no shadow, and no
  decorative gradient.
- Use the canonical light and dark warning tokens rather than the SDK's older amber aliases.
- Apply that canonical warning-token migration consistently to existing Report warning states;
  all warning surfaces should use the same brand-accurate palette.
- Keep `Score published` and the success receipt: the partial score was persisted; the
  adjacent notice explains why it is not directly comparable with a full-run score.

## Design note

- The submission result remains the existing public `LeaderboardScore`. Notebook-only
  context is carried by private, equality-neutral `ClientNotice` values so it cannot alter
  the persisted Scoreboard payload, public repr, or value semantics.
- `ClientNotice` is a reusable internal primitive with a stable code, `info` or `warning`
  severity, title, and body. OME-922 migrates only its own advisory; converting unrelated
  client warnings is deliberately separate scope.
- Notebook presentation uses the shared host-environment capability detector. Evaluation
  progress retains its established, separately named `ipykernel_loaded` capability because
  it can safely fall back when a rich panel cannot be constructed.
