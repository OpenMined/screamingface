---
ticket: OME-866
stack: scoreboard + screamingface (cross-stack; one branch/PR — the wire contract flips atomically)
status: in_progress
started: 2026-08-18
finished:
---

# OME-866 — Replace binary accuracy submissions with benchmark-native Leaderboard scores

## Intent

The Client → Scoreboard submission contract assumes every benchmark is binary accuracy
(`accuracy = correct/total`, 0..1). Only IFEval fits; DRACO's fractional scores (0.399)
and HealthBench's negative scores (-1.143) are rejected by the client adapter before
HTTP. The Engine benchmark is the sole authority for the final `CandidateResult.score`;
the Client submits it unchanged and the Scoreboard stores/ranks it without recalculating.
Minimal scope agreed with owner (tester deadline): generic `score` contract + rename;
typed `metrics` + score-presentation metadata deferred to a follow-up. Six design deltas
vs the ticket recorded as a Linear comment (2026-08-18) for Keelan's confirmation.

## Planned changes

Scoreboard (`apps/scoreboard`):
- `scores/models/score.py` — `accuracy` → `score`; `correct_questions` nullable;
  index `(benchmark_id, accuracy)` → `(benchmark_id, score)`.
- `scores/models/baseline.py` — `accuracy` → `score`.
- `scores/migrations/` — new migration for both tables (S1: same iteration).
- `scores/schemas.py` — `ScoreSubmission.score` (strict float, `allow_inf_nan=False`,
  finite validator, NO range), `correct_questions: int | None`, drop ratio
  model-validator; rename in `ScoreSchema`, `LeaderboardEntry`, `BaselineSchema`,
  `FrontierPoint`, `BaselineImportRow` (0..1 validator → finite; benchmark-native rule).
- `scores/store.py` — kwargs, `_content_hash` (hash submitted score directly),
  leaderboard query columns + ORDER BY.
- `scores/frontier.py` — field rename.
- `routes/scores.py` — remove ±0.01 cross-check + `ACCURACY_TOLERANCE`.
- Other `accuracy` consumers found by grep (import CLI, seeds, routes).
- `portal/benchmark.js`, `portal/leaderboard-logic.js`, portal HTML — "Accuracy" →
  "Score", plain-number formatting (no %), bar width min..max-normalized, clamped ≥ 0.

Client (`packages/screamingface`):
- `leaderboard.py` — public dataclasses `accuracy` → `score`; `_accuracy` validator →
  finite-only; `correct_questions` optional.
- `_scoreboard/leaderboards.py` — drop `_accuracy_result`; submit
  `candidate_result.score` verbatim as `score` (reject `None`/non-finite via
  `math.isfinite` before HTTP); decoders renamed; no `correct_questions`.
- `_ui/leaderboard_view.py` — plain-number score cell, min..max bar, clamp ≥ 0.
- Keep SDK idiom: frozen dataclasses + hand-rolled decoders (NO pydantic — owner call).

## Test plan

- RED first, both stacks. Cross-stack contract shapes per registered benchmark:
  IFEval 0.5, DRACO 0.399, HealthBench -1.143 — real client payload through Scoreboard
  validation (422-free), round-trip unchanged.
- Boundaries: NaN/±inf rejected both sides; `score=None` unrankable (client raises
  before HTTP); ranking DESC with negative and mixed ranges; equal scores.
- Presentation: negative/mixed/equal ranges in the client widget and portal
  `leaderboard-logic` Node tests (bar widths ∈ [0,100], no % formatting).
- Invariants defended: never recompute/normalize the Engine score; metrics never become
  ranking inputs; revisions never rank together (existing tests stay green).
- Existing accuracy-shaped tests updated to the new contract — sanctioned public
  contract change (owner approved 2026-08-18); no weakening, only renames + new cases.

## Acceptance

- DRACO 0.399 and HealthBench -1.143 submit end-to-end and round-trip byte-identical.
- IFEval still submits and ranks correctly.
- Public wire + UI say `score`, not `accuracy`; no 0..1 constraint anywhere.
- Both stacks' gates green (`run_gates.py scoreboard` + `run_gates.py screamingface`,
  incl. portal Node tests).
- Migration applies on a populated DB (live IFEval rows preserved).

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus: `apps/scoreboard/tests/unit/test_benchmark_native_scores.py`
  (new cross-stack contract tests), `apps/scoreboard/src/scoreboard/scores/migrations/0006_benchmark_native_scores.py`
  (rename + nullable + index, verified to preserve a live row written at 0005),
  `apps/scoreboard/DEPLOYMENT.md` + `packages/screamingface/README.md` (wire-contract prose),
  `packages/screamingface/scripts/build_notebooks.py` + regenerated examples 00/06/07/08/09
  (opt-in "Send the score to the Scoreboard" cells — owner-requested mid-implementation).
- **Commits:** one squash-ready commit on `OME-866-benchmark-native-scores`
  (`feat(scoreboard,screamingface): submit and rank benchmark-native scores`).
- **Gates:** `run_gates.py scoreboard` ALL GREEN (316 passed + 19 portal Node tests);
  `run_gates.py screamingface` ALL GREEN (882 passed, cov ≥95, notebooks deterministic,
  build + distribution checks). Migration chain 0001→0006 applied on fresh and populated
  sqlite; legacy row's accuracy value survives under `score`.
- **Deviations:**
  - `--skip-append-only` used once: the sanctioned public-contract rename touched prior
    tests (fixtures/keys renamed; three tolerance-era tests rewritten to pin the inverse
    invariant, never silently deleted). Owner approved the contract change 2026-08-18.
  - `tortoise-dev` companion skill (mandatory in the card) is not installed; the migration
    follows the house pattern of 0004/0005 instead. Propose installing the plugin.
  - Ticket deltas (total_questions kept, metrics deferred, hash identity, NaN guards,
    negative rendering, baseline scale) recorded as a Linear comment for Keelan's review.

## Follow-up (same unit, post-review): report_view percent fix

Code review of PR #626 found the Report card still rendering `CandidateResult.score`
through `_percent()` — HealthBench showed "-114.3%" directly above the submit receipt
showing "-1.143". Fixed on owner instruction (Khoa, 2026-08-18).

- **Files:** `src/screamingface/_ui/report_view.py` (new shared `_score_text`, score
  cell now benchmark-native), `src/screamingface/_ui/score_view.py` (reuses
  `_score_text` — one formatter for both sibling cards), `tests/test_report_panel.py`
  (2 new native-rendering tests; 3 prior percent-pin assertions updated — they pinned
  the pre-OME-866 percent contract this ticket retires; second sanctioned
  `--skip-append-only`, same owner approval as above).
- **Gates:** `run_gates.py screamingface --skip-append-only` ALL GREEN (885 passed).
- **Left as-is (out of scope):** axis scores still render via `_percent`
  (`report_view.py` `_axis_row`); the fusion-edge gilding rule `score > 0` never gilds
  negative-scale boards; pre-push hook does not gate the screamingface stack at all —
  gates were run manually.

## Follow-up (same unit): Filip's PR #626 review, both passes on `bf7f12f`

All 8 findings verified against the codebase before acting; 7 addressed in the working
tree (uncommitted — owner reviews manually before any commit), 1 is a release-ordering
owner action.

- **P1 loader:** `examples/helpers.py::load_candidate_result` now carries
  `status`/`refusal`/`stop_reason`/`rounds_executed` and reconstructs `failures`, so
  exported reports with refused/failed Cases reopen without tripping the CaseResult
  outcome contract. New `tests/test_examples_helpers.py` (round-trips a mixed
  scored/refused/failed export through the real helper file).
- **P1 IFEval description:** the Markdown rewrite in
  `apps/url4-cloud/.../ifeval/definition.py` reverted to the merge-base prose (portal
  renders descriptions via `textContent`; also the only out-of-app change on this PR —
  a prose improvement belongs on its own ticket per the repo rule).
- **P2 precision:** one score formatter — `report_view._score_text` (`%g`, 6 sig
  digits) is now imported by `leaderboard_view` (its local `.4g` copy deleted) and
  mirrored by `portal/main.js::formatScore` (`toPrecision(4)`→`(6)`). Direction chosen:
  6 digits everywhere (the exact Engine figure, e.g. `-1.1429`), not rounding the
  notebook down to 4 — existing receipt tests pin `-1.1429`.
- **P3 gilding:** `scored = score is not None` (was `> 0`); zero and negative gild.
  `test_a_zero_score_is_not_gilded` rewritten to
  `test_any_finite_score_is_gilded_zero_and_negative_included` — it pinned the retired
  0..1 rule; third sanctioned append-only exception, same owner approval, pending
  owner's manual review of the diff.
- **P2/P3 docs:** DEPLOYMENT.md smoke payload nests `client{}`; breaking-migrations
  section now lists `0006`. public-docs Leaderboard pages (learn/, sf-client/guides/,
  sf-client/api/, plus one line on sf-client/Index.vue) moved to `score` +
  benchmark-native wording; binary-tolerance validation paragraphs replaced.
- **Gates:** screamingface 889 passed / 1 skipped; scoreboard 318 passed / 2 skipped;
  portal Node 19 passed. public-docs not built (text-only template edits).
- **Owner actions:** release sequencing — cut `screamingface` 0.2.0 only from a commit
  including this PR (0.1.1 clients 422 after the flip); 0006 rollout needs the
  maintenance-window/expand-contract choice already noted above.
