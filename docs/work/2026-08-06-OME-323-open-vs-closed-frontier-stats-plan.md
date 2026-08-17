---
ticket: OME-323
stack: scoreboard
status: in_progress
started: 2026-08-06
finished:
---

# OME-323 — plan the open-vs-closed frontier stats implementation

## Intent

`docs/spec/2026-07-16-open-vs-closed-frontier-stats-spec.md` (resolved 2026-07-17,
currently landing in unmerged PR #414) settled both open questions: classification is
a static, fail-closed provider/model registry seeded from the OME-428 HF-vs-OpenRouter
precedent (§4), and "the frontier" means a trend over time, not a point-in-time
snapshot (§6). This unit produces the `docs/plan/` artifact translating that spec into
concrete scoreboard changes — a classification registry, a frontier-trend computation
over `Score`+`Baseline` rows, a read endpoint, and a minimal portal stat placement — so
implementation can start on explicit approval. No product code in this unit.

## Planned changes

- `docs/plan/2026-08-06-open-vs-closed-frontier-stats-plan.md` (new)

## Test plan

N/A — plan-only artifact, no code path in this unit.

## Acceptance

- Plan doc translates every spec section (§4 registry, §5 scope, §6 trend, §7
  non-goals, §8 acceptance) into concrete file-level changes grounded in the current
  `apps/scoreboard` codebase (models, store, routes, portal).
- Plan is presented to Filip for explicit approval before any implementation commit.

## Revision (2026-08-06, same day) — updated against nine spec follow-up resolutions

Before implementation started, a deeper review of the resolved spec against real
production data surfaced nine dilemmas the original §4/§6 text hadn't actually
covered (see `docs/work/2026-07-17-OME-323-resolve-classification-spec.md`'s Round 2
and the amended spec on PR #414). Updated this plan to match all nine:

- Added **Phase 0** (new): an `openness_override` column on `Score`/`Baseline` +
  migration — the one place this feature now needs a schema change.
- **Phase 1:** confirmed (not assumed) the closed-if-any-provider-closed mixed-fusion
  rule; added staleness logging for the fail-closed default; added override-aware
  `classify_score`/`classify_baseline` wrapping the registry internals.
- **Phase 2:** split `compute_frontier` into two independent passes — current split
  over all rows, trend walk over Score rows only (Baselines never become the trend
  holder); trend now advances only on a strict accuracy improvement, not a tie.
- **Non-goals/Acceptance:** added the verification/anonymous-submission risk as an
  explicit accepted non-goal; added acceptance criteria for the tie rule, the
  baseline/trend split, and the override field.
- **New Follow-ups section:** the OME-428/OME-394 Linear cross-link and the
  production data cleanup (§10) — both owner-driven, neither part of this PR's code.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** `docs/plan/2026-08-06-open-vs-closed-frontier-stats-plan.md`
  (substantially revised, see above).
- **Commits:** none yet — pending explicit approval to proceed to implementation.
  The plan doc itself stays uncommitted until implementation starts, same as before
  this revision — it lands together with Phase 0–4's code in one PR, mirroring how
  the spec (unlike this plan) got its own dedicated PR (#414) only because it was
  asked for explicitly.
- **Gates:** N/A (no code path touched).
- **Deviations:** none.
