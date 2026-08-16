# OME-775 — Implementation plan

**Spec:** `docs/spec/2026-08-16-OME-775-flat-benchmark-registration.md`
· **Ledger:** `docs/work/2026-08-16-OME-775-register-flat-benchmarks.md`
· **Branch:** `OME-775-register-flat-benchmarks` · **Stack:** scoreboard

Gates (from `.claude/sdlc.local.md`), run after every step:
`python3 .claude/scripts/run_gates.py scoreboard --base origin/main`
→ append-only · ruff check · ruff format --check · pyright · pytest --cov=scoreboard --cov-fail-under=80

Companion skill `tortoise-dev` is **mandatory** for this unit (models + migration).

## Ordering principle

Schema first, then the resolution rule, then identity, then ranking, then config. Each step is
RED-first and leaves the suite green before the next begins. Steps 2–5 each change one observable
behaviour, so a regression bisects to one step.

---

### Step 1 — schema: two nullable columns + migration

**RED:** a test asserting `Benchmark.revision` and `Score.benchmark_revision` exist, default to
`None`, and that a `Score` row can be created without either.

**GREEN:**
- `scores/models/benchmark.py` — `revision = fields.CharField(max_length=64, null=True)`
- `scores/models/score.py` — `benchmark_revision = fields.CharField(max_length=64, null=True, db_index=True)`
  with a WHY comment covering D4 (nullable because legacy demo entries and `OME-322` imports
  genuinely have no revision).
- `scores/migrations/0004_*.py` — two `ops.AddField`, `dependencies = [("models", "0003_auto_20260713_1505")]`,
  `initial = False`. Built-in Tortoise migrations, never Aerich.

**Guard:** confirm `makemigrations` reports no *further* drift after the hand-written migration.

---

### Step 2 — the resolution rule (typed field + metadata fallback)

**RED:**
- a submission with the typed top-level `benchmark_revision` stores it;
- a submission carrying it **only** in `metadata` (today's Client shape, F5) stores it too;
- top-level wins when both are present and disagree;
- a non-string or empty `metadata.benchmark_revision` resolves to `None` rather than raising;
- a submission with neither is accepted and stores `None`;
- the `metadata` dict is **not** mutated or stripped — the copy stays.

**GREEN:**
- `scores/schemas.py` — `ScoreSubmission.benchmark_revision: str | None = None`.
- `scores/store.py` — one `_resolve_benchmark_revision(submission)` helper implementing the
  three-step order from spec §4.3; `_submission_to_kwargs` persists it.

**Why a named helper:** §4.4 needs the same resolved value, and the rule must not be written twice.

---

### Step 3 — identity: revision joins `_content_hash` (D3)

**RED:**
- two submissions identical but for `benchmark_revision` produce **different** hashes and both
  persist (today they collide and the second is discarded);
- two identical submissions still dedup;
- a submission carrying the revision in metadata hashes the same as the equivalent typed one —
  i.e. identity follows the resolved value, not its wire position.

**GREEN:** add `"benchmark_revision": _resolve_benchmark_revision(submission)` to the `identity`
dict; extend the existing WHY comment to say why revision is identity while the rest of `metadata`
is not, and to record the no-backfill consequence (D3) in place.

**Explicitly not done:** no backfill of stored `content_hash` values.

---

### Step 4 — ranking partitions by `(spec_id, benchmark_revision)`

**RED:**
- one spec with two revisions returns **two** ranked entries, each best-within-its-revision (today:
  one entry, the higher accuracy winning across an incomparable boundary);
- rows with `NULL` revision group together exactly as before — the backward-compatibility guard;
- existing single-revision ordering and `MAX_LEADERBOARD_TOP` behaviour unchanged;
- the per-spec history route still resolves.

**GREEN:** `_build_leaderboard_query` — `RowNumber().over(scores.spec_id, scores.benchmark_revision)`.

---

### Step 5 — expose on read paths

**RED:** `benchmark_revision` appears on the leaderboard entry, per-spec history and score read
schemas; absent revision serialises as `null`, not omitted.

**GREEN:** additive fields on the read schemas, following `OME-770`'s pattern. Portal untouched.

---

### Step 6 — seed config

**RED:** `SeedBenchmark` accepts an optional `revision`; `load_benchmarks_json` rejects an unknown
key (`extra="forbid"` already) and accepts the three real entries; re-running the seed is idempotent
and does not duplicate.

**GREEN:**
- `seed.py` — `revision: str | None = None` on `SeedBenchmark`, threaded into
  `store.register_benchmark(...)`;
- `store.register_benchmark(..., revision: str | None = None)` into the `update_or_create` defaults;
- `charts/scoreboard/values.yaml` — append the three entries from spec §4.8, **keeping** the three
  legacy demo entries (D2). Revisions copied verbatim from the Engine definitions.

**Revision values** are read from `apps/url4-cloud/.../{draco,ifeval,healthbench}/definition.py` at
implementation time rather than transcribed here, so the plan cannot drift from the source.

---

### Step 7 — close-out

- Fill the ledger Outcome (files, commits, gates, deviations).
- Conventional commits, body `Refs: OME-775`, no `Co-Authored-By`.
- Open the PR; squash-merge on green CI + approval; never `--admin`.
- Close-comment on OME-775 per the card's `close_template`; close the `docs/tasks/` mirror.

## Risks

| Risk | Handling |
|---|---|
| Dedup identity changes the night before launch (D3) | Steps 3 and 4 are separate commits with independent tests, so either can be reverted alone without unpicking the schema. |
| The chart's seed list is the only thing that unblocks Monday | Step 6 is last but is also the smallest and least coupled — if time runs out, it can land as its own PR ahead of the rest. |
| Hand-written migration drifts from the models | Step 1's guard runs `makemigrations` and asserts no further drift. |

## Out of scope

Retiring legacy demo benchmarks · backfilling hashes or revisions · portal rendering · any Client
change (it already sends the revision).
