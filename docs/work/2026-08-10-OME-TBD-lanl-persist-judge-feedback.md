---
ticket: OME-TBD  # Linear waived by owner 2026-08-10 (workspace issue quota); backfill when possible
stack: url4-cloud
status: done
started: 2026-08-10
finished: 2026-08-10
---

# OME-TBD — Persist the lanl-ensemble judge's corrective feedback in the case trace

## Intent

The judge (synthesizer) feedback that drives every correction round is generated,
interpolated into the round-N+1 member prompts, and discarded — `member-record` and the
case envelope keep only deterministic verifier text. When a correction round fails, the
trace cannot show whether the judge misdiagnosed, wrote vague guidance, or wrote good
guidance the members ignored (acute on the case-1122 phantom round, where the judge's
confusion had to be inferred from downstream artifacts). Owner approved persisting it.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py` (or wherever
  the lanl expression template is built) — continuation outcome gains
  `judge: '$judge_feedback_N.output'`; no new model calls or endpoints.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/corrective_policy.py` — bump
  `LANL_ENSEMBLE_REVISION` (protocol expression changed).
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/runtime.py` — `_lanl_envelope`
  accepts the optional `judge` field per continuation outcome.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/case_evaluation.py` — carry judge
  text per attempt through `bind_case_evaluation`.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/aggregate.py` — additive
  `metadata.attempts[n].judge_feedback` (null when no judge ran before that attempt).
- Tests appended in the touched areas' unit files.

## Test plan

- RED: envelope accepts `{check, judge, next}` continuation outcome and the bound case
  carries the judge text on the attempt it preceded.
- RED: aggregate `metadata.attempts` exposes `judge_feedback` (null for attempt 1;
  text for corrected attempts).
- RED: lanl expression template contains the `judge:` binding and the bumped revision.
- Guards: outcome without `judge` (old shape) still validates? — NO: revision bump means
  old shape never reaches new code path in production; decide leniency in DESIGN.
- All prior tests green and unmodified.

## Acceptance

- A corrected case's report shows the judge's actual words per round.
- `LANL_ENSEMBLE_REVISION` bumped; suite + gates green on changed files.
- Live lanl run (owner-run) shows `judge_feedback` populated on a corrected case.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `iterative_correction.py` — gated outcome struct gains `judge: $judge_feedback_N.output`
    (both mid-chain and final-attempt shapes).
  - `runtime.py` — new `_continuation_outcome` helper decodes `{check, judge?, next?}`,
    validates judge is text, stamps `judge_feedback` onto the attempt's check record
    (also resolved the envelope's complexity-gate breach my change caused, plus the
    file's pre-existing import-block I001 via ruff --fix — whitespace only).
  - `aggregate.py` — `metadata.attempts[n].judge_feedback` (additive; None when no judge).
  - `corrective_policy.py` — untouched after all: owner reverted the planned v2 bump
    (2026-08-10) — revision pins SCORE meaning, and judge_feedback is trace-only, so
    the id stays `lanl-early-exit-ensemble-v1` and the revision hash is unchanged.
  - Tests appended: 3 in `test_ifeval_lanl_ensemble.py` (envelope stamping, non-text
    judge rejected, expression carries the binding), 1 in
    `test_ifeval_iterative_correction.py` (aggregate exposes judge_feedback). All RED
    first, all GREEN after; no prior test modified.
- **Commits:** fce496dd — feat(url4-cloud): persist the lanl-ensemble judge's feedback in the case trace
- **Gates:** suite 988 passed / 5 skipped; coverage 93.01% (≥80); ruff check+format and
  pyright clean on all touched files.
- **Deviations:** Linear ticket waived by owner (quota); backfill later. Live proof of a
  populated judge_feedback needs a paid run on a round-1-failing case — owner-run.
