# OME-770 (pass 1 of 2) — Implementation plan

Spec: `docs/spec/2026-08-12-OME-770-run-cost-field.md` · Ledger:
`docs/work/2026-08-12-OME-770-run-cost-field.md`

**Written retroactively (2026-08-13)** alongside the spec — see that file's preamble and the
ledger's Deviations. Steps 1–4 were executed on 2026-08-12; step 5 on 2026-08-13 in response to
review findings.

One SDLC unit, one stack (`scoreboard`), backend only. RED before GREEN at every step.

## Step 1 — GREEN: the column

`src/scoreboard/scores/models/score.py` — `run_cost_usd` on **`BaseScore`** (the abstract half),
beside the other submission fields, per the model's existing Rule-2 split:

```python
run_cost_usd = fields.DecimalField(max_digits=12, decimal_places=6, null=True)
```

Anchors required on it: `WHY` Decimal-not-Float, `WHY` these bounds, `INVARIANT` NULL≠0,
`AIDEV-NOTE` excluded from `content_hash`.

## Step 2 — the migration (stack rule S1, same iteration)

```sh
uv run tortoise makemigrations --name add_run_cost_usd   # Tortoise 1.1.7 built-in, NEVER Aerich
uv run tortoise migrate
```

This repo resolves config from `[tool.tortoise]` in `pyproject.toml`, so no `-c` flag. A single
`ops.AddField` for a nullable column — no backfill (spec §2, D3). Verify: applies from an empty
database, and a second `migrate` is a no-op.

## Step 3 — RED then GREEN: the schema layer

`tests/unit/scores/test_schemas.py` first:

- a valid cost round-trips; **absent** is accepted and stays `None`; a **negative** is rejected;
- `0` is accepted and stays `0` — proving zero and absent are distinct, not merged (spec §2.1);
- `0.000123` survives without float drift, and a four-figure cost is not truncated — the two ends
  of the range that motivated `decimal_places=6`.

Then `src/scoreboard/scores/schemas.py` — the field on `ScoreSubmission` (with bounds),
`ScoreSchema`, and `LeaderboardEntry`.

## Step 4 — RED then GREEN: the store

`tests/unit/scores/` first:

- cost persists and returns from `leaderboard()` and `list_for_spec()`;
- a submission without one yields `None` there, not `0`;
- **dedup invariant:** two submissions identical except for `run_cost_usd` still collapse to one
  row (spec §3).

Then `src/scoreboard/scores/store.py` — persist in `_submission_to_kwargs` (with a comment that it
is deliberately outside `_content_hash`), carry through `_score_to_schema` and **both** projections
in `_build_leaderboard_query`.

## Step 4a — the trap this plan originally missed

`src/scoreboard/routes/leaderboard.py` was **not** in the original plan and had to be added:
`RankedLeaderboardEntry` mirrors `LeaderboardEntry` field-for-field plus `rank`, and `_ranked_entry`
splats one into the other. Because both set `extra="forbid"`, adding the field to the schema alone
produced a **500 on the read path** — not a type error, and invisible to pyright. Found by driving
the live endpoint. Leave an `AIDEV-NOTE` on the class.

## Step 5 — review findings (2026-08-13)

Three findings, all verified against the running app before fixing:

1. **RED then GREEN — precision bounds.** `ge=0` alone let `0.0000009` be silently rounded,
   `1000000` be accepted backend-dependently, and `1e30` return a `500` (spec §2.2). Add
   `max_digits=12, decimal_places=6` to the `ScoreSubmission` field; assert all three are now
   `422`, and that the documented bounds still pass.
2. **RED then GREEN — the history read path.** `HistorySubmission` and `_history_submission()` were
   missed, so `GET .../history` silently omitted the cost the spec's acceptance criteria require.
   Add the field and map it.
3. **A cross-DTO guard.** The `RankedLeaderboardEntry`/`HistorySubmission`/`ScoreSchema`
   duplication has now caused **two** separate defects — a 500 (step 4a) and a silent omission
   (finding 2). Add `test_every_score_field_reaches_at_least_one_read_dto`, asserting every `Score`
   column appears on at least one read DTO, with an explicit allowlist for the deliberately
   unpublished ones (`content_hash`, the FK object, the reverse relation). This turns the next
   occurrence into a failing test instead of relying on someone noticing.

## Step 6 — gates and close

`uv run .claude/scripts/run_gates.py scoreboard --base origin/main` — all green. Fill the ledger
Outcome (actual vs planned files, gate results, deviations), then commit with `Refs: OME-770`.

## Risks

- **The generated migration may not satisfy this repo's lint settings as emitted.** It didn't —
  `ruff check` flagged `I001`. Fix the generated file, never relax the gate.
- **The read-DTO duplication is a latent trap for every future field** (step 4a). Step 5's guard is
  the mitigation.
- **Pass 2 stays blocked** on links 1–3 of the spec's §1 chain regardless of this unit's outcome.
