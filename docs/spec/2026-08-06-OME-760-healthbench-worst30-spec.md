---
title: OME-760 — HealthBench worst-30% challenge exam
status: accepted
created: 2026-08-06
ticket: OME-760
related:
  - https://linear.app/openmined/issue/OME-760/add-the-healthbench-worst30-engine-exam-per-item-gpt-54-judging
  - https://linear.app/openmined/issue/OME-759/ship-the-healthbench-worst-30percent-challenge-exam-on-the-sf-engine
  - docs/spec/2026-08-05-OME-712-screamingface-engine-benchmark-runtime.md
  - docs/plan/2026-08-06-OME-760-healthbench-worst30-plan.md
  - docs/work/2026-08-06-OME-760-healthbench-worst30-engine-exam.md
---

# HealthBench worst-30% challenge exam

## Purpose

The Engine gains a physician-authored health-conversation exam built for the entry
challenge: open-source Fusions try to beat our best open-weights Fusion on the 157
hardest HealthBench Professional rows. Grading reproduces OpenAI simple-evals'
per-rubric-item judge protocol byte-for-byte at the judge boundary; scoring is the
challenge metric (unclipped mean), never the official HealthBench score, and every
surface says so.

Protocol authority: `healthbench_eval.py` in openai/simple-evals (vendored reference)
plus the July 2026 production port (`screamingface-benchmarks`
`benchmarking/graders/healthbench_rubric.py`), congruence-audited in the design doc
(owner copy: `.dk/plans/2026-08-05-healthbench-sf.md`).

## Benchmarks

Two flat `screamingface.benchmark.v1` entries (OME-712 contract), sharing one prepared
asset set and one installer:

- **`healthbench/worst30`** — 157 cases pinned via `case_ids`; the challenge exam.
  Description carries: *challenge metric on the worst-30% subset — not an official
  HealthBench score*.
- **`healthbench/smoke`** — 1 pinned case (~3 judge calls); diagnostic only, never
  comparable, per the smoke-protocol doctrine.

The bare id `healthbench` stays reserved for the future official 525-row exam — same
assets, new entry.

## Cases

- Source: `openai/healthbench-professional`, HF revision
  `349962fd46dd02343a0d8a606491baf59154ea1a`, downloaded at image build
  (`Dockerfile.benchmark` stage), never at run time. Preparer deps pinned; the preparer
  version participates in the revision hash.
- `prepare.py` bakes assets for ALL 525 rows: public `cases.json` rows `{id, input}`
  where `input` is the candidate-input chat envelope carrying the row's native
  multi-turn messages; private `rubrics/<id>.json` holding the rubric items
  `{rubric_id, criterion, points, tags}`.
- The worst-30% subset (team-picked: ascending mean score over the July run's 15
  evaluators; provenance in `subset.py`) is a frozen tuple of 157 HF ids, hashed into
  the revision. `prepare.py` fails the BUILD if any subset id is missing, any points
  value is non-int, or any row lacks a positive-points item.
- Privacy: rubric text never appears in `cases.json`; the Candidate world has no rubric
  routes. Stated limitation: the dataset is public on HF — the boundary keeps the
  Engine honest, it is not anti-cheat.

## Grading protocol (congruent with simple-evals)

- One judge call per rubric item, items independent. Judge model
  `openrouter/openai/gpt-5.4` (floating slug; the reference's internal snapshot pin is
  a named deviation), declared to the installer for route validation.
- The Engine pre-renders the official GRADER_TEMPLATE verbatim into ONE finished prompt
  per item: `<<conversation>>` = the `"role: content"` transcript with the Candidate's
  answer appended as the final assistant turn; `<<rubric_item>>` = `[<points>]
  <criterion>` (ints render without a decimal). The judge call carries the finished
  prompt as context with an EMPTY intent — the Runner maps intent to a system message,
  and the official professional judge sends none.
- No temperature or reasoning param is pinned: the official professional judge sends
  only `reasoning={"effort":"low"}` (not expressible through the gateway yet — named
  deviation) and no sampling params. Provider-default temperature is load-bearing:
  retries must draw fresh samples. `max_tokens` is an Engine-side safety bound only.
- Judge reply: strip ```json fences, parse, accept only strict-boolean `criteria_met`.
  Bounded retry (2 re-asks). An item still unresolved fails its ROW loudly — never a
  default verdict. Rationale: a default `False` on a negative-points item erases a
  penalty and INFLATES the score. Row ids ride the expression intent; the judge never
  sees or supplies ids.

## Scoring (challenge metric)

- Case score: Σ points of met items / Σ positive points, negatives subtract,
  UNCLAMPED (reference `calculate_score`).
- Exam score: mean of case scores, UNCLIPPED (deviation from the official
  `max(0, mean)` clip — on this subset every serious baseline mean is negative and the
  clip would flatten the leaderboard to 0.00). Sample stdev (n−1) when reported.
- `verdict_coverage` is reported; a challenge attempt is valid only at coverage 1.0.
- A missing or unreadable rubric asset produces a FAILED case result that reaches the
  aggregate — never a silently dropped case (inherited B1 rule).
- Named omissions vs the paper: no length-adjusted score (the paper's primary metric),
  no tag-level metrics, 1 answer sample vs the paper's 8.

## Out of scope

Official 525-row exam · challenge ops (credits, leaderboard) · gateway reasoning-effort
parameter · the baseline rerun that publishes the target number (OME-762, human-run).
