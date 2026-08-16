# OME-775 — Flat benchmark registration + revision identity

**Ticket:** [OME-775](https://linear.app/openmined/issue/OME-775/register-draco-ifeval-and-healthbench-in-the-scoreboard-benchmark)
· **Ledger:** `docs/work/2026-08-16-OME-775-register-flat-benchmarks.md`
· **Stack:** scoreboard · **Date:** 2026-08-16

## 1. Problem

Scoreboard's benchmark registry seeds only `hle` / `livetruth` / `livetruth-latest` — legacy demo
entries. The Engine advertises `draco`, `ifeval`, `healthbench-worst30`. Consequences today, on the
live dev board:

- The Leaderboard v1 catalogue renders three demo boards and none of the real ones.
- A Client submission for a real benchmark fails with `unknown_leaderboard` **after** a successful
  Engine evaluation — the failure lands at the end of the user's run, not the start.

The public launch is 2026-08-17.

Separately, the board has no notion of *which revision of a benchmark* a score was produced
against, so results from incompatible dataset/protocol revisions would rank against each other as
if comparable.

## 2. Established facts

Verified against `origin/main`; none assumed. Full table in the ledger. The three that drive the
design:

- **F5 — the revision already arrives.** The Client sends `benchmark_revision` on every submission,
  nested in the free-form `metadata` dict (`packages/screamingface/.../leaderboards.py:333`).
  Unlike `OME-770`'s cost field, there is no upstream dependency to wait on. This work *promotes an
  existing untyped wire value*, it does not invent one.
- **F7 — dedup deliberately ignores `metadata`.** `_content_hash` (`scores/store.py:75-96`) hashes
  benchmark_id, spec_id, url4_expression, the result numbers and provider order, with an explicit
  WHY comment excluding metadata. So the revision currently has no effect on identity.
- **F8 — ranking is revision-blind.** `RowNumber().over(scores.spec_id)` (`store.py:106-114`).

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Build the full ticket, including revision partitioning — not seeding alone | Owner call, 2026-08-16, taken with F4/F5 known. |
| D2 | Keep `hle` / `livetruth` / `livetruth-latest` registered alongside the three real benchmarks | Owner call. Retiring them is not this unit's business and would need a copy decision. |
| D3 | `benchmark_revision` **joins** the dedup identity hash; **no backfill** | Owner call, taken with the trade-off stated: forward-correct identity, at the cost that a resubmitted pre-existing recipe creates a second row rather than deduping. The alternative silently discards a second-revision result, which defeats the partitioning this unit adds. |
| D4 | Every new column is **nullable**; no backfill migration | Legacy demo entries (D2) have no Engine revision, and `OME-322`'s imported LMArena baselines genuinely never ran at any revision. Same reasoning `OME-770` applied to cost and `OME-391` to `content_hash`. |
| D5 | The typed field is **additive**, and `metadata.benchmark_revision` remains accepted | Making the typed field authoritative-and-exclusive would break every currently-deployed Client, which sends it only in metadata. Forbidding the metadata copy would `422` live submissions — the failure mode `OME-820` was reviewed for. |
| D6 | Ranking **partitions** by revision rather than filtering to the registered revision | See §5. |

## 4. Design

### 4.1 `Benchmark.revision`

```python
revision = fields.CharField(max_length=64, null=True)
```

`register_benchmark()` and `SeedBenchmark` gain an optional `revision`. The chart's seed list
carries the Engine's computed `REVISION` for the three real benchmarks; the retained legacy three
carry none (D2 + D4).

### 4.2 `Score.benchmark_revision`

```python
benchmark_revision = fields.CharField(max_length=64, null=True, db_index=True)
```

Indexed because §4.5 partitions on it.

### 4.3 `ScoreSubmission.benchmark_revision` — typed, optional

Added as `str | None = None`. Resolution order on submit:

1. the typed top-level field, when present;
2. otherwise `metadata["benchmark_revision"]` when it is a non-empty string;
3. otherwise `None`.

Step 2 is what keeps today's Client working (F5, D5). Step 3 is the legitimate legacy/import case
(D4). The metadata copy is **not** stripped or rejected — it stays where it is.

### 4.4 `_content_hash` gains the resolved revision (D3)

The `identity` dict gains `"benchmark_revision": <resolved value from §4.3>`. The existing WHY
comment is extended to say why revision belongs to identity while the rest of `metadata` does not:
a different benchmark revision is *a different thing measured*, not incidental provenance.

No backfill. Stored hashes stay as computed. The bounded consequence is documented in the code
comment and the ledger, not left for a reader to rediscover.

### 4.5 Ranking partitions by `(spec_id, benchmark_revision)`

`RowNumber().over(scores.spec_id)` becomes `.over(scores.spec_id, scores.benchmark_revision)`.

Best-per-spec becomes best-per-spec-per-revision, so two revisions of one spec surface as separate
ranked entries instead of one silently beating the other across an incomparable boundary.

**Rejected alternative — filter to the benchmark's currently-registered revision.** Stricter, and it
reads more literally as "not ranked together", but it *hides* submitted scores rather than
separating them, and under D2 the retained legacy entries have a null registered revision, so the
rule would empty their boards. Partitioning is also backward-safe: every existing row has a null
revision, so they group exactly as they do today.

### 4.6 Read paths expose it

`benchmark_revision` is added to the leaderboard entry, per-spec history and score read schemas,
following the additive pattern `OME-770` used for cost. The portal is **not** changed in this unit.

### 4.7 Migration

One Tortoise migration `0004_*` (built-in migrations, never Aerich), adding two nullable columns and
the index. Idempotent seeding is unchanged — `register_benchmark` already uses `update_or_create`.

### 4.8 Seed values

| id | display_name | dataset_url |
|---|---|---|
| `draco` | DRACO | `https://huggingface.co/datasets/perplexity-ai/draco` |
| `ifeval` | IFEval | none — the dataset is vendored in the Engine, no single public URL is asserted |
| `healthbench-worst30` | HealthBench Worst-30% Challenge | `https://huggingface.co/datasets/openai/healthbench` |

Display names and revisions are taken verbatim from the Engine definitions (F1–F3) so the registered
identity matches the Engine's exactly, as the ticket's acceptance requires.

## 5. Out of scope

- Retiring the legacy demo benchmarks (D2).
- Backfilling `content_hash` or revision on existing rows (D3, D4).
- Portal rendering of the revision (§4.6).
- Any change to the Client — it already sends what is needed (F5).

## 6. Acceptance

- `GET /v1/benchmarks` advertises `draco`, `ifeval`, `healthbench-worst30` plus the retained legacy
  entries.
- A real Client `CandidateResult` for each family submits without `unknown_leaderboard`.
- Registered IDs and revisions match the Engine definitions exactly.
- Two scores for one spec at different revisions do not rank against each other.
- A submission carrying the revision only in `metadata` is still accepted and still gets it promoted.
- Re-running the seed job neither duplicates nor corrupts benchmark records.
- Full gates green.
