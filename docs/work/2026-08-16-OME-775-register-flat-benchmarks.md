---
ticket: OME-775
stack: scoreboard
status: done
started: 2026-08-16
finished: 2026-08-16
---

# OME-775 — Register DRACO, IFEval and HealthBench in the Scoreboard catalogue

## Intent

Scoreboard's benchmark registry seeds only the legacy `hle` / `livetruth` / `livetruth-latest`
demo entries, so the Leaderboard v1 catalogue renders three demo boards instead of the real ones
and a Client submission for a real benchmark fails with `unknown_leaderboard` after a successful
Engine evaluation. Register the three canonical flat benchmarks the Engine now advertises, and
give the board the revision identity it needs so scores from incompatible benchmark revisions are
not ranked against each other.

Launch-critical: the public launch is 2026-08-17 and the live board today advertises no real
benchmark.

## Facts established before design (all verified against `origin/main`, not assumed)

| # | Finding | Evidence |
|---|---|---|
| F1 | The Engine's canonical IDs are now flat: `draco`, `ifeval`, `healthbench-worst30` | `apps/url4-cloud/.../{draco,ifeval,healthbench}/definition.py` — `BENCHMARK_ID`. Flattened by OME-836/837/838, all merged 2026-08-14. |
| F2 | Titles are `DRACO`, `IFEval`, `HealthBench Worst-30% Challenge` | same files, `title=` |
| F3 | Each Engine benchmark computes an immutable `REVISION` sha256 over its dataset + protocol (+ verifier for IFEval) revisions | `definition.py` — `REVISION = hashlib.sha256(...)` |
| F4 | Scoreboard's `Benchmark` model has **no** revision field | `scores/models/benchmark.py` — id, display_name, description, dataset_url, created_at only |
| F5 | The Client **already sends** `benchmark_revision` on every submission — nested inside the free-form `metadata` dict | `packages/screamingface/.../leaderboards.py:333` — `"metadata": {"benchmark_revision": candidate_result.benchmark.revision, ...}` |
| F6 | `ScoreSubmission` is `extra="forbid"` with no typed revision field, so F5 arrives untyped and unvalidated | `scores/schemas.py:74-92` |
| F7 | **`_content_hash` deliberately excludes `metadata`** — so the revision does not participate in dedup identity | `scores/store.py:75-96`, and the explicit WHY comment at :76-78 |
| F8 | The leaderboard query partitions by `spec_id` alone, ordered by accuracy — no revision awareness | `scores/store.py:106-114`, `RowNumber().over(scores.spec_id)` |
| F9 | Seeding is chart-driven config, applied by a Job from `SCOREBOARD_SEED_BENCHMARKS_JSON` | `charts/scoreboard/values.yaml:98-116`, `templates/job-seed-benchmarks.yaml`, `src/scoreboard/seed.py` |

F5 is the load-bearing good news: unlike `OME-770`'s cost field, the data already flows. This is a
promotion of an existing untyped wire value to a typed one, not a new upstream dependency.

F7 is the load-bearing risk — see the open decision below.

## Owner decisions taken (2026-08-16)

- **D1 — build the whole ticket as written**, including revision partitioning, not just the seed
  config. (Owner's call, taken with F4/F5 known.)
- **D2 — keep the legacy `hle` / `livetruth` / `livetruth-latest` entries registered** alongside
  the three real benchmarks rather than retiring them for launch.

## D3 — does `benchmark_revision` join the dedup identity hash (`_content_hash`)?

Discovered after D1 was taken, and it materially changed the unit's blast radius, so it was
escalated rather than assumed either way. **Resolved below.** The two options as they stood:

- **If it does not join:** two runs of the same recipe at two different benchmark revisions hash
  identically, so the second dedups into the first and its result is silently discarded — the
  partitioning this ticket adds would then never see the second revision at all. This is the same
  shape as the `OME-770` "case B" hole recorded on that ticket.
- **If it does join:** identity is forward-correct, but every `content_hash` already stored was
  computed without the revision, so stored hashes no longer match what the current code would
  compute for the same payload. Consequence is bounded (a resubmitted pre-existing recipe creates
  a second row instead of deduping) but it is a silent semantic change to a value `OME-391`
  established as the board's immutability backstop.

Recorded rather than decided unilaterally, per the 95% confidence gate.

**RESOLVED 2026-08-16 — the revision joins `_content_hash`, with no backfill.** Owner's call, taking the
forward-correct identity over the alternative that silently discards a second revision's result.
The bounded consequence (a resubmitted pre-existing recipe creates a second row rather than
deduping) is recorded in a code comment beside the hash, not left to be rediscovered.

## Planned changes

Per `docs/plan/2026-08-16-OME-775-flat-benchmark-registration.md`, seven steps: schema+migration →
resolution rule → identity → ranking partition → read paths → seed config → close-out.

## Test plan

Per the plan — RED-first at every step. Contracts pinned: revision resolution from either wire
shape, identity separating revisions while preserving `OME-391` dedup, the ranking partition, and
the NULL-revision backward-compatibility guard.

## Running deviations

1. **Step 5's leaderboard-entry exposure was pulled forward into Step 4.** The plan separated the
   ranking partition from exposing the field on read schemas, but the partition is not observable
   without it — a test can only see "two rows instead of one", not *which* revisions, so the
   assertion would have been far weaker than the invariant deserves. `LeaderboardEntry` and
   `RankedLeaderboardEntry` therefore gained the field in Step 4. Step 5 keeps the remaining read
   paths (per-spec history, score read schema).
2. **Three pre-existing route tests failed during Step 4** because `_ranked_entry` splats
   `entry.model_dump()` into `RankedLeaderboardEntry`, which is `extra="forbid"`. Fixed by adding
   the field to the route model — the prior tests were not modified, and they pass unchanged.

## Acceptance

- `GET /v1/benchmarks` advertises `draco`, `ifeval`, `healthbench-worst30` (plus the retained
  legacy demo entries, per D2).
- A real Client `CandidateResult` for each family submits without `unknown_leaderboard`.
- Registered IDs match the Engine result identity exactly (F1).
- Scores from incompatible benchmark revisions are not ranked together.
- Re-running the seed job does not duplicate or corrupt benchmark records.
- `OME-768` renders the three board shells from the live API.
- Full gates green.

## Outcome

- **Actual files:** as planned, 15 files / +852 −1. Production: `scores/models/{benchmark,score}.py`,
  `scores/migrations/0004_auto_20260816_0630.py`, `scores/schemas.py`, `scores/store.py`,
  `seed.py`, `routes/leaderboard.py`, `charts/scoreboard/values.yaml`. Tests:
  `tests/unit/scores/{test_models,test_store}.py`, `tests/unit/{test_seed,test_leaderboard_routes}.py`.
  Plus the spec, plan and this ledger. No unplanned production file was touched.

- **Commits** (7, in order):

  | sha | message |
  |---|---|
  | `2a205e65` | docs(scoreboard): spec and plan the flat benchmark registration |
  | `d0f14e05` | feat(scoreboard): carry the Engine benchmark revision on benchmarks and scores |
  | `e9d4d073` | feat(scoreboard): resolve the benchmark revision from either wire shape |
  | `aa18554b` | feat(scoreboard): make the benchmark revision part of dedup identity |
  | `edd2586b` | feat(scoreboard): rank each benchmark revision separately |
  | `df2e4e57` | feat(scoreboard): expose the benchmark revision on the remaining read paths |
  | `39765054` | feat(scoreboard): register DRACO, IFEval and HealthBench with their revisions |

- **Gates:** `run_gates.py scoreboard --base origin/main` run after every step — append-only ✓,
  ruff check ✓, ruff format ✓, pyright ✓, pytest --cov=scoreboard --cov-fail-under=80 ✓.
  Final suite **190 passed, 2 skipped**. Two commits (`df2e4e57`, `39765054`) ran with
  `--skip-append-only`; see deviation 3.

- **Verification beyond the unit tests.** The seed config is deploy-time YAML that no unit test
  executes, so it was proven end to end instead of assumed:
  1. `helm template` renders all six benchmarks into `SCOREBOARD_SEED_BENCHMARKS_JSON`.
  2. That **rendered** payload — not a hand-written fixture — was fed through the real
     `load_benchmarks_json` + `seed_benchmarks`, producing 6 rows with the right revisions, and
     **6 rows again after seeding twice** (idempotency).
  3. The three revisions were diffed **programmatically** against the Engine definitions
     (`ALL MATCH`) to rule out transcription drift, rather than eyeballed.
  4. `tortoise makemigrations` reported **"No changes detected"** against the hand-written
     migration, proving `0004` matches the models exactly.

### Deviations

1. **Step 5's leaderboard-entry exposure moved into Step 4.** The ranking partition is not
   observable without the field on the entry — a test could only assert "two rows instead of
   one", never *which* revisions — so the assertion would have been weaker than the invariant
   deserves. Step 5 kept the remaining read paths.
2. **Four read-DTO construction sites needed the field, not the two the plan implied.**
   `ScoreSchema`, `LeaderboardEntry`, `RankedLeaderboardEntry`, `BenchmarkSchema` and both
   `_*_to_schema` helpers build by explicit mapping under `extra="forbid"`, so each surfaced as
   a failing test rather than silently defaulting. Caught by the suite, not by review.
3. **The append-only gate was skipped on two commits, with owner approval, for one edit.**
   `test_get_spec_history_returns_submissions_newest_first` pins the exact key set of the
   history payload, which §4.6 legitimately extends. Escalated per sdlc rule 5 rather than
   quietly edited. The assertion **remains exact** — it gained one member and was deliberately
   NOT loosened to a subset check, which would have traded a real guarantee for convenience.
   The gate has no per-change acknowledgement mechanism, only a whole-check skip; the skip is
   recorded in both commit messages. Step 6's own test diff was **47 insertions, 0 deletions**.
4. **`ifeval` is registered with no `dataset_url`.** Its dataset is vendored inside the Engine
   (`url4_cloud.benchmarks.ifeval.vendor`), so no single public URL is authoritative. Left null
   rather than inventing one; flagged to the owner at spec time.

### Follow-ups (not filed — owner decision)

- **The portal does not render the revision.** Out of scope per §5, but the board can now show
  one spec twice with no visible explanation. Worth a ticket before the revision actually
  differs in production.
- **Legacy demo benchmarks remain registered** (D2). A launch-copy decision, not a technical one.
- **No backfill of `content_hash`** (D3): resubmitting a recipe that predates this change creates
  a second row instead of deduping. Bounded and documented in code; file if it ever bites.
