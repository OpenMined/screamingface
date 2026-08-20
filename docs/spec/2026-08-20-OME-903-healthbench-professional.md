# OME-903 — Serve the whole HealthBench Professional exam, scored the official way

Status: approved (owner, 2026-08-20) · Stack: screamingface-engine

> Before/After diagram: on the Linear issue
> ([OME-903](https://linear.app/openmined/issue/OME-903/add-the-full-healthbench-benchmark-all-525-cases-with-the-official)) —
> "worst30 vs full-525 — what exists, what's new". Not duplicated here.

## 1. Problem

The Engine serves exactly one HealthBench board, and it is deliberately incomparable to
every published HealthBench number:

| Fact | Where | Consequence |
|---|---|---|
| The served exam is the frozen 157-row worst-30% list | `benchmarks/healthbench/subset.py:20` | A reader cannot line our board up against a paper that ran all 525 |
| The exam-level metric is the UNCLIPPED mean | `benchmarks/healthbench/scoring.py:73-78` | Scores go negative; the official metric floors at 0 |
| Both facts are baked into the revision hash | `benchmarks/healthbench/definition.py:58-75` | Changing either in place would silently redefine the existing board |

A fan asking "how good is this Fusion, really?" gets a number that exists nowhere else.

## 2. The assets already hold the whole exam

The expensive half — downloading, validating, and baking 525 conversations plus 525
physician-written rubrics — is done and shipping today:

| Piece | Where | State |
|---|---|---|
| All 525 cases + 525 rubric files baked at image build | `benchmarks/healthbench/prepare.py:168-215` | ✅ exists — `emit()` writes EVERY HF row, ids 1..N in file order |
| worst30 is a serve-time filter, not a build fork | `benchmarks/healthbench/runtime.py:342-350` | ✅ `_select_cases(raw, case_ids)` |
| Candidate → judge → verdict → per-case score chain | `benchmarks/healthbench/runtime.py:66-137` | ✅ every route already takes `case_ids`, `benchmark_id`, `benchmark_revision` as parameters |
| Per-case scoring math | `benchmarks/healthbench/scoring.py:16-70` | ✅ identical for both boards (the reference `calculate_score`) |
| Exam-level mean | `benchmarks/healthbench/aggregate.py:172-197` | ⛔ hardcodes `unclipped_mean` |
| Route constants + revision hash | `benchmarks/healthbench/definition.py:31-86` | ⛔ module-level, worst30-only |
| Registry entry | `benchmarks/builtins.py:14-20` | 🆕 one line |

So "the full version" is a **second benchmark identity over the same immutable answer
key** — no new dataset pin, no second bake, no new grading code.

## 3. Locked decisions

1. **Dataset = the 525 already-baked `openai/healthbench-professional` rows** at the
   pinned revision. NOT the 5,000-row main set, NOT the 1,000-row Hard split. (Owner,
   2026-08-20.)
2. **Score = the official clipped mean.** The reference aggregates with
   `np.clip(mean, 0, 1)`; per-case scores are unclamped and bounded above by 1.0, so the
   lower clip is the one that bites. worst30 keeps its unclipped challenge metric.
3. **Separate leaderboard.** New benchmark id, new revision, own scoreboard entry.
   worst30's id, revision, and score meaning are untouched.
4. **Benchmark id = `healthbench-professional`**, title "HealthBench Professional".
   (Owner, 2026-08-20.) It matches the dataset name and stays clear of `healthbench`,
   which is the shared ASSET family name the SDK's `prepare` CLI already uses.
5. **The mid-run check surface is advertised, unchanged** — same criterion
   `healthbench-pass.v1`, same 0.5 threshold, served under the new benchmark's own route.
   (Owner, 2026-08-20.) Capability parity with worst30: a `corrective_loop` recipe runs on
   either board, and the cost of doing so on 525 cases is the submitter's call, refused
   nowhere silently.

## 4. The contract this unit ships

- A `Benchmark` registered as `healthbench-professional`, `case_count = 525`, selecting
  Engine case ids `1..525` (the 1-based positions `prepare.py` numbers by).
- Its own `REVISION`, hashed over the same inputs worst30 uses, differing in exactly three
  of them: the case selection fingerprint, the protocol revision string, and the scoring
  rule name. Same dataset pin, same preparer revision, same judge pinning, same grader
  template bytes.
- Its own route prefix `/benchmarks/healthbench-professional/<revision>/…`, so both boards
  install into one Runner world without collision.
- An aggregate that reports `clipped_mean` where worst30 reports `unclipped_mean`.
  Everything else in the reduction — per-case scoring, coverage, failure visibility,
  refusal handling — is the shared code, unchanged.
- A build-time assertion that the baked file really holds 525 rows, so a dataset that
  grows or shrinks fails the image build instead of silently serving a 526-case exam
  under a 525-case identity.

## 5. Non-goals (deliberately out of this unit)

- **The scoreboard seed entry** (`apps/scoreboard/charts/scoreboard/values.yaml`) — a
  second landing label, so a scoreboard sub-issue per the cross-cutting rule. It consumes
  the `REVISION` this unit computes.
- **An SDK example notebook** for the new board — optional follow-up.
- **Any paid run.** This ships with free/offline tests only; paid runs are owner-executed.
- **Re-tuning anything about worst30**, including its threshold, metric, or subset.

## 6. Don't regress

- worst30 keeps its frozen 157-case list, unclipped metric, and current revision hash —
  no existing submission becomes incomparable. A test pins the current hash value.
- The baked assets stay one immutable answer key: both boards select from the same
  `cases.json`; no renumbering, no second bake, no build fork.
- The judge stays pinned identically on both boards (model, params, retry rules, grader
  template bytes), so the only differences between them are case selection and the final
  clip.
- Installing both benchmarks into one Runner world must not collide on any route or on
  the shared assets root.
