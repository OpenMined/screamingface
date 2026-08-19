# OME-874 — implementation plan

Spec: `docs/spec/2026-08-18-OME-874-mvp-landing-copy.md` · Stack: scoreboard ·
Worktree: `.claude/worktrees/OME-874-mvp-landing-copy` (branched `origin/main` @ `e51e9ced`)

Ordered so each step is independently green. Steps 1–2 are backend and carry the only migration;
3–5 are the page; 6 is the gate sweep.

## Step 0 — vendor the hero mark

Only `sf-mark-640.png` exists upstream (415 KB, 608×640). Every other filename I probed returns an
identical 211 KB body — an SPA fallback served as `200`, not an image. So there is exactly one
source asset.

- `curl` it to `apps/scoreboard/portal/assets/mark/sf-mark-640.png`.
- Resample to `sf-mark-128.png` (`sips -Z 128`) — the mark renders at `.46em` of a
  `clamp(44px,…,76px)` hero, so ~35 px tall at most; 128 px is a 2× cushion. Resampling is not
  redrawing, which is what the brand rule forbids.
- `apps/scoreboard/portal/assets/mark/PROVENANCE.md` — source URL, fetch date, the resample command.
- Confirm `src/scoreboard/portal.py` serves `portal/assets/**` (it serves the directory tree; the
  artifact allowlist governs `artifacts/`, not `portal/`). **RED first:** a test asserting
  `GET /assets/mark/sf-mark-128.png` is 200 before the file is added.

## Step 1 — `focus` on Benchmark (RED → GREEN)

- **RED:** `tests/unit/scores/test_models.py` — a `Benchmark` accepts `focus`; it defaults `None`.
  `tests/unit/test_benchmarks_routes.py` — `/v1/benchmarks` exposes `focus`, `null` when unset.
- **GREEN:** `models/benchmark.py` `focus = fields.CharField(max_length=120, null=True)`;
  `BenchmarkSchema` gains `focus: str | None`; the route projection passes it through.
- **Migration `0007`** — single `ops.AddField`, parent `0006_benchmark_native_scores`. Nullable, no
  backfill, exactly as `revision` was added in `OME-775`. Not breaking: adding a nullable column is
  safe under the `pre-upgrade` rollout that `DEPLOYMENT.md` documents, unlike `0005`/`0006`.
- `scoreboard.seed` accepts `focus` in `--benchmarks-json`.

## Step 2 — seed values

- `charts/scoreboard/values.yaml` — `focus` on the three Engine benchmarks, using §6.3's proposed
  copy **pending owner edit**; legacy demo entries left without one.
- Same caveat as `OME-775`: deployed environments keep their own values file, so this needs the
  platform team to sync. Note it in the PR body rather than assuming it propagates.

## Step 3 — the page (`index.html`)

One edit pass, top to bottom:

| Element | From | To |
|---|---|---|
| crumb | `portal` | `leaderboard` |
| rail links | `<nav class="rail-nav">` wrapper | direct children + `.rail-link--end` on `docs` |
| eyebrow | `Benchmark receipts` | `Leaderboard` |
| `<h1>` | `Results you can reproduce, not just read.` | `Fusi<img class="o-mark" src="assets/mark/sf-mark-128.png" alt="o">ns, ranked and reproducible.` |
| — | — | **new** `<dl class="kv defs">`, 3 rows, `.dt-repro` on the first `<dt>` |
| `.note` | the `OME-820` self-reported disclaimer | mockup's `Read this first`, kicker `Read this first` |
| CTA | plain link, `screamingface.ai` | `.btn` *"Get started with ScreamingFace →"* → `docs.screamingface.ai` |
| table head | `Benchmark · Fusions · Dataset · Leaderboard` | `Benchmark · Focus · Fusions · Best reproducible · Dataset · Open` |

`benchmarks` keeps targeting `index.html#benchmarks`; the stats strip and the Dataset column stay;
the footer's second cell stays dropped — all four carried from `OME-839` with reasons in the spec.

## Step 4 — `main.js`

- `benchmarkRow(b, board)` gains the `focus` cell (`—` when null) and the `Best reproducible` cell.
- `fetchSubmissionCount` currently discards everything but the length of the payload it already
  fetched. Rename to `fetchBoard` and return `{count, best}` where `best = entries[0].score` —
  **entries only, not baselines** (spec §5). No new request; the N+1 is unchanged.
- Reuse `formatScore` (6 significant digits, shared with the SDK since `OME-866`); `—` when absent.

## Step 5 — `portal.css`

Two rules, tokens only:
- `.kv .dt-repro { color: var(--success-text-low); }` — verbatim from the mockup's `board.css`.
- `.rail .rail-link--end { margin-right: var(--space-7); }`.

`.defs` gets no rule — it has none upstream either; it stays as a hook.

## Step 6 — tests and gates

- `tests/portal/index-rows.test.js` — new: focus renders, `—` when null; best score renders, `—`
  when no entries; a baseline-only benchmark shows `—` rather than the baseline's score.
- `tests/unit/test_portal_static.py` — the hero mark is served and referenced relatively; the page
  contains no `brand.screamingface.ai` URL (no off-origin asset).
- Full `run_gates.py scoreboard` (ruff · ruff format · pyright · pytest ≥80% · portal node tests).
- Migration chain `0001→0007` on a fresh **and** a populated sqlite.
- Manual: light and dark, ≥1280 px and 620 px (the `.kv` breakpoint), mark aligned on the baseline.

## Risks

1. **The `.kv` glossary collapses to one column below 620 px.** Already handled upstream; verify the
   green `dt-repro` key still reads as a key there.
2. **`.note` is the one shadowed component.** It is terminal chrome and legitimately carries
   `--shadow-window`; do not "fix" it to match the flat rule.
3. **`focus` copy is unwritten.** Ships `null` → `—` if the owner does not supply values; the column
   is still correct, just empty.

## Not in this unit

Cost chart (`OME-822`) · functional pool toggle (`OME-771`) · verification signal (`OME-821`) ·
`OME-871` is superseded by step 3's hero row and should be closed once this merges.
