---
ticket: OME-775
stack: scoreboard
status: in_progress
started: 2026-08-16
finished:
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

## Open decision — blocks the spec

**Does `benchmark_revision` join the dedup identity hash (`_content_hash`)?**

Discovered after D1 was taken, and it materially changes the unit's blast radius, so it is not
assumed either way.

- **If it does not join:** two runs of the same recipe at two different benchmark revisions hash
  identically, so the second dedups into the first and its result is silently discarded — the
  partitioning this ticket adds would then never see the second revision at all. This is the same
  shape as the `OME-770` "case B" hole recorded on that ticket.
- **If it does join:** identity is forward-correct, but every `content_hash` already stored was
  computed without the revision, so stored hashes no longer match what the current code would
  compute for the same payload. Consequence is bounded (a resubmitted pre-existing recipe creates
  a second row instead of deduping) but it is a silent semantic change to a value `OME-391`
  established as the board's immutability backstop.

Recorded here rather than decided unilaterally, per the 95% confidence gate.

## Planned changes

_Pending the open decision above and the spec. Not started._

## Test plan

_Pending spec._

## Acceptance

- `GET /v1/benchmarks` advertises `draco`, `ifeval`, `healthbench-worst30` (plus the retained
  legacy demo entries, per D2).
- A real Client `CandidateResult` for each family submits without `unknown_leaderboard`.
- Registered IDs match the Engine result identity exactly (F1).
- Scores from incompatible benchmark revisions are not ranked together.
- Re-running the seed job does not duplicate or corrupt benchmark records.
- `OME-768` renders the three board shells from the live API.
- Full gates green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** <vs planned>
- **Commits:** <sha — message>
- **Gates:** <run_gates.py result line / counts>
- **Deviations:** <anything that differed from the plan, or "none">
