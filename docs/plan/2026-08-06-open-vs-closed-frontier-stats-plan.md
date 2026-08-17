# Open vs. closed frontier statistics — Implementation Plan

**Ticket:** OME-323 · **Spec:** `docs/spec/2026-07-16-open-vs-closed-frontier-stats-spec.md`
(resolved 2026-07-17, extended 2026-08-06 with nine follow-up resolutions — §4, §6,
§7, §8 updated, new §9 manual override + §10 pre-launch cleanup — currently landing
in unmerged PR #414, see Risk below)
**Goal:** Compute, from real `Score`/`Baseline` rows, what share of each benchmark's
accuracy frontier is held by open-reproducible stacks vs. proprietary ones — both the
current split and the trend over time — and expose it via the scoreboard API + portal.
**Architecture:** A classification registry (`scoreboard/classification/openness.py`)
classifies each `Score` (by `ran_with_providers`, closed-if-any-provider-closed) and
`Baseline` (by `model_name`), fail-closed for anything unrecognized and logging every
time that fail-closed default actually fires. A per-row `openness_override` column
lets an operator correct a specific row without a code deploy. A pure
frontier-computation function runs two independent passes: the *current* open/closed
split over all rows, and a *trend* walk over Score rows only (never Baselines, whose
`imported_at` isn't a trustworthy timestamp), advancing the holder only on a strict
accuracy improvement (a tie never moves it). Exposed as a new read endpoint, rendered
as one additional stat card on the existing benchmark portal page. Marketing-site
(`screamingface-web`) integration, real score verification, and the rich 2D/3D trend
chart (OME-324) are explicitly out of scope (spec §7).
**Tech stack:** Same as the rest of scoreboard — Python 3.12, FastAPI, Tortoise ORM,
pytest + ruff + pyright.

## Phase 0 — Manual classification override (spec §9, new)

- [ ] Migration: add `openness_override: str | None` (`"open"` | `"closed"` | `null`)
  to both `Score` and `Baseline` models (`scores/models/score.py`, `baseline.py`),
  plus the corresponding Tortoise migration — created and committed in this same
  iteration per Stack rule S1. This is the **one** place this feature needs a
  migration; the registry/classification logic itself stays a pure code-side lookup
  (spec §7 non-goal, unchanged).
- [ ] Add `openness_override` to `ScoreSchema`/`BaselineSchema` (`schemas.py`),
  nullable. **Not** added to `ScoreSubmission` — this is an operator-only correction
  (set directly against the DB, or a future admin surface), never client-supplied at
  submission time.

## Phase 1 — Classification registry (spec §4)

- [ ] `apps/scoreboard/src/scoreboard/classification/__init__.py` + `openness.py`:
  - `Openness = Literal["open", "closed"]`.
  - `classify_providers(providers: list[str]) -> Openness` — **closed if any provider
    is closed; open only if every provider is open** (spec §4's mixed-provider rule,
    confirmed 2026-08-06 — not an implementation assumption anymore, an actual
    decision).
  - `classify_baseline_name(model_name: str) -> Openness` — same fail-closed pattern
    via substring match.
  - **Staleness logging (spec §4, new):** both functions log (e.g.
    `logger.warning("unrecognized provider/model for openness classification: %r",
    name)`) every time the fail-closed default actually fires for a name the
    registry doesn't recognize — a visible signal instead of silent, permanent
    undercounting as new models ship.
  - `classify_score(score: ScoreSchema) -> Openness` / `classify_baseline(baseline:
    BaselineSchema) -> Openness`: check `openness_override` (Phase 0) first — if set,
    return it outright, registry never consulted; else defer to
    `classify_providers`/`classify_baseline_name`. These two are what Phase 2 and the
    tests actually call — `classify_providers`/`classify_baseline_name` are the
    registry's internals.
  - Registry stays a plain module-level tuple/set of markers.
- [ ] Unit tests (`tests/unit/classification/test_openness.py`): known-open,
  known-closed, mixed-provider (one open + one closed → closed), unrecognized →
  closed **and logged** (assert the log record fires, not just the return value), an
  `openness_override` set on a row wins outright over what the registry alone would
  have said (both directions — forcing open, forcing closed).

## Phase 2 — Frontier trend computation (spec §5, §6)

- [ ] `apps/scoreboard/src/scoreboard/scores/frontier.py`:
  - `FrontierPoint`: `{at: datetime, accuracy: float, openness: Openness, holder:
    "score", label: str}` (`label` = `spec_id`; `holder` is always `"score"` now —
    see below).
  - `compute_frontier(scores: list[ScoreSchema], baselines: list[BaselineSchema]) ->
    FrontierResult`, where `FrontierResult = {current: FrontierPoint | None, trend:
    list[FrontierPoint], open_count: int, closed_count: int, open_share: float}`.
    **Two independent passes, not one merged timeline:**
    1. **Current split** — `open_count`/`closed_count`/`open_share` computed over
       **all** rows, Scores (via `classify_score`) *and* Baselines (via
       `classify_baseline`) together. This is the "how much of the frontier is open
       right now" number the ticket asks for.
    2. **Trend** — walks **Score rows only**, ordered by `submitted_at`. Baselines
       never enter this walk at all (spec's baseline-timing resolution:
       `imported_at` isn't a real-world timestamp, so a Baseline must never become
       "the current holder" via the trend — not merely "excluded from the printed
       list"). Emits a new `FrontierPoint` only on a **strict** improvement
       (`accuracy > running_best`) — an exact tie leaves the existing holder in
       place (spec's tie-breaking resolution; matters on real data today: the live
       board already has two submissions tied at 100%).
  - Pure function, no I/O — directly unit-testable without a DB.
- [ ] `ScoreStore.list_all_for_benchmark(benchmark_id: str) -> list[ScoreSchema]` —
  new query alongside the existing best-per-spec `leaderboard()`, reusing
  `_score_to_schema`. Deliberately **benchmark-wide across all `spec_id`s** (spec's
  frontier-scope resolution, confirmed 2026-08-06) — this is not an oversight
  relative to the leaderboard's own per-spec ranking, it's the spec's literal scope.
- [ ] Unit tests (`tests/unit/scores/test_frontier.py`): empty benchmark (no
  scores/baselines → empty trend, `current=None`, no crash); single score; a Baseline
  with higher accuracy than any Score still counts in the current split but never
  becomes `current`'s holder; a later-but-lower-accuracy Score row absent from the
  trend; **exact-tie regression test** — two Scores, identical accuracy, different
  openness, holder does not change on the second one; `openness_override` on a Score
  changes both which bucket it counts in AND, if it's the frontier holder, the
  `openness` reported at that trend point.

## Phase 3 — Read endpoint (spec §5)

- [ ] New response schema in `schemas.py`: `FrontierResponse` (`benchmark_id`,
  `open_count`, `closed_count`, `open_share`, `current: FrontierPoint | None`,
  `trend: list[FrontierPoint]`), following the file's existing `extra="forbid"`
  convention.
- [ ] `GET /v1/leaderboard/{benchmark_id}/frontier` in `routes/leaderboard.py`,
  reusing `_get_benchmark_or_404`; calls `ScoreStore.list_all_for_benchmark` +
  `BaselineStore.list_baselines` + `compute_frontier`.
- [ ] Tests (`tests/unit/test_leaderboard_routes.py`): 404 for unknown benchmark,
  empty-benchmark 200 with an empty trend and `current: null`, response-shape
  stability.

## Phase 4 — Portal stat card (spec §5 "render it somewhere")

- [ ] Extend the existing `#leaderboard-summary` stats row (`portal/benchmark.html`)
  with one more `.s` card — "Open frontier share" (e.g. "73% open") — sourced from
  the new endpoint in `benchmark.js`. No new charting library; a stat tile, not the
  trend chart (OME-324's job per spec §7).
- [ ] No portal unit tests exist today for this page (untested vanilla JS) — matches
  existing practice; not introducing a JS test harness in this unit.

## Non-goals (spec §7)

- Rendering on the `screamingface.ai` marketing site (separate `screamingface-web`
  repo).
- Backfill/migration for the registry's own classification logic (still true — the
  registry is a code-side lookup evaluated at read time; only Phase 0's
  `openness_override` column needs a migration, and that's additive, not a backfill).
- Syncing the registry with AI Gateway's own `hosted_shared` classification
  (OME-428/OME-394) — resolved as "ship now, cross-link the dependency" (see
  Follow-ups below), not implemented in this unit.
- Real score/claim verification for the public claim — ship as-is; unverified and
  even anonymous submissions affect this stat exactly as they already affect the rest
  of the leaderboard today. A separate, much larger, already-unowned effort.
- OME-324's 2D/3D frontier charts.

## Acceptance (spec §8)

- Split + trend computed from real `Score`/`Baseline` rows only, no mock data in the
  code path.
- Registry is deterministic and unit-tested, including the fail-closed default and
  its logging.
- A mixed-provider `Score` is classified closed-if-any-provider-closed.
- The frontier trend never moves the holder on an exact accuracy tie.
- Baselines are included in the current split, excluded from the trend walk.
- `openness_override` is respected by the classification path and ships with its
  migration in this same unit.
- Exposed via the scoreboard API/portal; marketing-site integration explicitly
  deferred.

## Follow-ups (owner-driven, not part of this PR's code)

- **Linear cross-link (spec §4):** post a comment on OME-428 and OME-394 pointing at
  scoreboard's registry and this ticket, so whoever eventually builds AI Gateway's
  own classification sees the dependency in their own ticket rather than a
  scoreboard doc they'd have no reason to read. Can happen anytime — not blocking
  this unit's implementation.
- **Production data cleanup (spec §10):** delete the known smoke-test row
  (`spec_id: score-007-smoke`, confirmed live on `scoreboard.screamingface.ai`) and
  any other junk data from production **before** this feature computes its first
  real public number. A direct write against live production data — its own
  explicitly-confirmed action, separate from this code PR, not something this unit
  does automatically.

## Risk / dependency

- **PR #414 (the spec itself) is still unmerged.** Implementation should wait for it
  to merge so `docs/spec/` on `main` matches what the code claims to implement. #414
  now carries nine additional resolved decisions (this plan is built against all of
  them) and is pending review — Irina Bejan (product/policy content: the
  classification rules and the accepted verification/gaming-risk tradeoffs) plus
  CODEOWNERS (sergio-bershadsky/HupBaHa, auto-requested).

## Ticket

No new sub-issues — single unit, same ticket (`OME-323`), same
branch/worktree used for this plan doc (`OME-323-open-vs-closed-landing-page`).
Phases 0–4 ship as one PR, not a cascade — the scope is one app, one cohesive
feature, unlike the url4-cloud-runner epic's multi-app spread.
