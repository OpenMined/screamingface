# OME-770 (pass 1 of 2) — Implementation plan

Spec: `docs/spec/2026-08-12-OME-770-run-cost-field.md` · Ledger:
`docs/work/2026-08-12-OME-770-run-cost-field.md`

**Written retroactively (2026-08-13)** alongside the spec — see that file's preamble and the
ledger's Deviations. Steps 1–5 were executed on 2026-08-12; steps 6–8 on 2026-08-13 in response to
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

## Step 5 — the trap this plan originally missed

`src/scoreboard/routes/leaderboard.py` was **not** in the original plan and had to be added:
`RankedLeaderboardEntry` mirrors `LeaderboardEntry` field-for-field plus `rank`, and `_ranked_entry`
splats one into the other. Because both set `extra="forbid"`, adding the field to the schema alone
produced a **500 on the read path** — not a type error, and invisible to pyright. Found by driving
the live endpoint. Leave an `AIDEV-NOTE` on the class.

## Step 6 — review findings (2026-08-13)

Three findings, all verified against the running app before fixing:

1. **RED then GREEN — precision bounds.** `ge=0` alone let `0.0000009` be silently rounded,
   `1000000` be accepted backend-dependently, and `1e30` return a `500` (spec §2.2). Add
   `max_digits=12, decimal_places=6` to the `ScoreSubmission` field; assert all three are now
   `422`, and that the documented bounds still pass.
2. **RED then GREEN — the history read path.** `HistorySubmission` and `_history_submission()` were
   missed, so `GET .../history` silently omitted the cost the spec's acceptance criteria require.
   Add the field and map it.
3. **A cross-DTO guard.** The `RankedLeaderboardEntry`/`HistorySubmission`/`ScoreSchema`
   duplication has now caused **two** separate defects — a 500 (step 5) and a silent omission
   (finding 2). Add `test_every_score_field_reaches_at_least_one_read_dto`, asserting every `Score`
   column appears on at least one read DTO, with an explicit allowlist for the deliberately
   unpublished ones (`content_hash`, the FK object, the reverse relation). This turns the next
   occurrence into a failing test instead of relying on someone noticing.

## Step 7 — code-review findings, pass 1 (2026-08-13)

Five findings, all verified against the code before acting. Two carried owner decisions
(spec §2.2 revision and §2.4); three are mechanical.

### 7a — RED then GREEN: quantize inexact, reject unstorable (spec §2.2 revision)

`Field(max_digits=…, decimal_places=…)` cannot express this — its constraints run *before* an
`after` validator, so `0.21000000000000002` would be rejected before any quantizing could happen.
So drop those two constraints from the field, keep `ge=0` and add `allow_inf_nan=False`, and put the
ordered rule from spec §2.2 in a `field_validator`. Order matters: the ceiling check must precede
`quantize()`, which raises `InvalidOperation` on an absurd exponent rather than returning a value.

Tests: `0.21000000000000002` → stored `0.210000`; `1.23456789` → `1.234568`; `0.0000009`,
`1000000`, `1e30`, `-1`, `NaN`, `Infinity` → `422`; `999999.9999996` → `422` (rounds up past the
ceiling); `0` → accepted and still `0`; `0.000001` → accepted (the boundary).

### 7b — RED then GREEN: fixed-scale wire form (spec §2.4)

One shared `RunCostUsd` annotated type carrying a `PlainSerializer`, used by all four read DTOs so
they cannot drift. `when_used="json"` only — `_ranked_entry` splats `entry.model_dump()` in Python
mode and must keep receiving a `Decimal`, not a string.

Tests: a cost submitted as `12.5` and one as `1e3` both read back `"12.500000"` / `"1000.000000"` on
the leaderboard route, the history route and `GET /v1/scores/{id}`; absent stays `null`.

### 7c — the raw-row loop converts only `ran_with_providers`

`store.leaderboard()` builds `LeaderboardEntry(**row)` from raw pypika rows; `run_cost_usd` arrives
as a SQLite string and survives only on Pydantic's lax `str → Decimal` coercion. Convert it through
the field's `to_python_value` alongside `ran_with_providers`, so `rows` is already typed for anything
that reads it before validation.

### 7d — the cross-DTO guard is a sync test under an asyncio `pytestmark`

Emits `PytestWarning` on every run today and becomes a hard error in a later pytest-asyncio. Make it
`async def`.

### 7e — coverage gap the review surfaced

The spec's acceptance names `GET /v1/leaderboard/{id}`, but only a store-level test asserts the cost
reaches it. Add an HTTP-level test on that route, matching the two the history route already has.

## Step 8 — code-review pass 2 (2026-08-13)

- **G1 sign-zero:** normalize any zero to a canonical positive `_ZERO_COST` in the validator **and**
  the read serializer. Both are required — the serializer covers rows already stored. Assert
  `is_signed()` and the rendered string, since `Decimal(0) == Decimal("-0")`.
- **G2 corrupt row:** guard the row-loop conversion (`InvalidOperation`/`ValueError` only), degrade
  that cost to `null`, log at warning. Do **not** guard the ORM read path — see spec 2.7.
- **G3 dead branch:** remove the unreachable post-quantize ceiling re-check; correct the test comment
  that claimed to exercise it.
- **G4 sub-quantum:** round away from zero instead of rejecting, as `max(quantize(v), COST_QUANTUM)`.
  Rewrite the two tests that asserted the old `422`.

Live probe must use `SCOREBOARD_DATABASE_URL` (not `..._DB_URL`) against a **file** DB with
`tortoise migrate` run first — lifespan does not create the schema, so `:memory:` fails with
"no such table". Run it twice from scratch and diff the output; identical output is the only proof the
probe is isolated.

## Step 9 — gates and close

`uv run .claude/scripts/run_gates.py scoreboard --base origin/main` — all green. Fill the ledger
Outcome (actual vs planned files, gate results, deviations), then commit with `Refs: OME-770`.

## Risks

- **The generated migration may not satisfy this repo's lint settings as emitted.** It didn't —
  `ruff check` flagged `I001`. Fix the generated file, never relax the gate.
- **The read-DTO duplication is a latent trap for every future field** (step 5). Step 6's cross-DTO guard is
  the mitigation.
- **Pass 2 stays blocked** on links 1–3 of the spec's §1 chain regardless of this unit's outcome.
