---
ticket: OME-770
stack: scoreboard
status: done
started: 2026-08-12
finished: 2026-08-13
---

# OME-770 (pass 1 of 2) — accept, store and expose a run cost on a submission

## Intent

`OME-770` wants a Cost column, Pareto frontier marks and a cost-vs-accuracy chart. None of it is
buildable because **no cost value reaches Scoreboard at all** — nothing cost-shaped exists on
`ScoreSubmission`, `Score`, or `LeaderboardEntry`.

Rather than wait on the whole upstream chain, this unit builds the half Scoreboard owns: a
**typed, nullable run cost** accepted on submission, persisted, and exposed on the leaderboard
read path. That lets the Client start sending cost the moment it can produce one, and turns
`OME-770`'s remaining work into pure rendering.

Nullable is the design, not a concession: `OME-770` already specifies `n/a for imported/unknown`,
so an absent cost is a *specified* state rather than missing data.

## Decisions locked (2026-08-12)

| # | Decision | Choice |
|---|---|---|
| D1 | Field name | `run_cost_usd`. The unit is in the name so no reader has to guess; `OME-770` renders `$x.xx` and `OME-303` mentions "monetary cost and currency", so if multi-currency ever lands it is a separate concern rather than a silent reinterpretation of this column. |
| D2 | Type | **`DecimalField`, not `FloatField`.** Money must not be binary floating point. `max_digits=12, decimal_places=6` — sub-cent precision matters (a smoke run can cost $0.0003) and the ceiling must clear real runs (Irina cited a $3–4k DRACO rerun), so 999,999.999999 covers both ends. Note `accuracy` is a `FloatField` and stays one: it is a ratio, not money. **Owner-confirmed 2026-08-12, with a display constraint:** full precision is stored, but the UI must **round** for display so a six-decimal figure cannot overflow the Cost column's width. That is a pass-2 rendering requirement — recorded here so it is not lost between passes. |
| D3 | Nullability | `null=True`, no backfill. Same reasoning `content_hash` already documents in this model: the column has to land on a table with existing rows. Absent ≠ zero — see D5. |
| D4 | Where the field lives | On `BaseScore` (abstract) beside the other submission fields, per the model's existing Rule-2 split. |
| D5 | Absent vs zero | A `None` cost means **unknown**, and must never be coerced to `0`. A run that genuinely cost nothing (fully cache-served — the "zero cost" goal in `OME-767`) is a legitimate `0`, and conflating the two would put an unknown-cost row at the cheapest end of the Pareto front. Rendering and frontier maths both have to treat `None` as "exclude / gutter". |
| D6 | Validation | Rejected at the schema layer with `ge=0`: a negative run cost is not a thing. Enforced in Pydantic rather than a DB check constraint, matching how the rest of this app validates. |
| D7 | **`content_hash` is NOT extended** | The hash covers recipe identity (benchmark, spec, url4, result numbers, provider order) and deliberately excludes client-supplied context. Cost is a property of *an execution*, not of the recipe — two runs of one recipe can cost different amounts and must still dedup to one row. Adding cost to the hash would silently break `OME-391`'s dedup guarantee. |
| D8 | Known limitation, accepted | Because of D7, a recipe already submitted **without** cost cannot later gain one: the resubmission dedups to the existing row. Verified in `store.py:232-234` — a dedup hit returns the stored row and never writes the incoming data, so the two cases are asymmetric: (A) first submission has a cost and later identical ones read it back; (B) first has none and a later cost is **silently discarded**, with the client receiving `created=False` and a null cost and no signal that its value was dropped. **Owner decision 2026-08-12:** accept this and do **not** add a dedup fill-in — keep `OME-391`'s immutability intact. The real fix is D10, which removes case B entirely for new recipes. |
| D10 | **Cost becomes mandatory later — follow-up required** | Owner direction 2026-08-12: *"we should work towards rejecting if cost is missing even on the first run after it is available."* A direct submission arriving with no cost, once the Client can emit one, is a client bug rather than a legitimate state. It cannot be required **now** for three reasons: nothing currently sends it (`OME-303` unmerged, no Engine roll-up, no Client field), so a required column would reject **every** submission including Stephen's documented smoke test and the verified `cloudflared` path; a `NOT NULL` column cannot be added to the already-populated table without inventing a cost for existing rows; and `OME-770` itself specifies `n/a for imported/unknown`, which imported `OME-322` baselines legitimately are. Target end state: **required on direct submissions, null only for imported/legacy rows.** Noted on the ticket. |
| D11 | Trust model for a self-reported cost | Owner decision 2026-08-12: **store it, expose it, and mark provenance in the UI** — never present it as verified. Cost is materially harder to verify than accuracy: a re-run tells us what *we* paid, not what the submitter paid, so a submitter understating cost lands on the cost-efficiency frontier for free. The frontier is therefore computed over self-reported numbers and the UI must say so, reusing the verified/unverified distinction the board already carries for accuracy — the mechanism `OME-771`'s Status column provides. |
| D9 | Scope split | **Backend only in this unit.** The frontier maths belongs in `portal/leaderboard-logic.js`, which exists only on the unmerged `OME-769` branch (PR #569) — writing it here would recreate a file already under review and guarantee a conflict. It follows once #569 lands. |

## Planned changes

- `apps/scoreboard/src/scoreboard/scores/models/score.py` — `run_cost_usd` on `BaseScore`.
- A migration under `apps/scoreboard/src/scoreboard/scores/migrations/` generated by the built-in
  CLI (`uv run tortoise makemigrations --name add_run_cost_usd`; Tortoise 1.1.7, **never Aerich**,
  and this repo resolves config from `[tool.tortoise]` in `pyproject.toml` so no `-c` flag).
  Per the card's stack rule S1 the migration ships in this same iteration.
- `apps/scoreboard/src/scoreboard/scores/schemas.py` — optional `run_cost_usd` on
  `ScoreSubmission` (with `ge=0`), exposed on `ScoreSchema` and `LeaderboardEntry`.
- `apps/scoreboard/src/scoreboard/scores/store.py` — persist on `submit()`, carry through
  `leaderboard()` and `list_for_spec()`.
- Tests under `apps/scoreboard/tests/unit/`.

## Test plan

RED first, against the existing pytest suite:

- **Schema:** a submission with a valid cost round-trips; **absent** cost is accepted and stays
  `None`; a **negative** cost is rejected; a `0` cost is accepted and stays `0` (D5 — proving zero
  and absent are distinct, not merged).
- **Precision (D2):** `0.000123` survives the round trip without float drift, and a four-figure
  cost is not truncated — the two ends of the range that motivated `decimal_places=6`.
- **Store:** cost persists and comes back on `leaderboard()` and `list_for_spec()`; a submission
  without cost yields `None` there rather than `0`.
- **Dedup invariant (D7):** two submissions identical except for `run_cost_usd` still collapse to
  one row — pinning that cost is outside recipe identity.
- **Migration:** `uv run tortoise migrate` twice; the second run is a no-op. Existing rows survive
  with `NULL` (no backfill).

## Acceptance

- A client can submit `run_cost_usd`; it persists and appears on `GET /v1/leaderboard/{id}` and the
  per-spec history.
- Omitting it is valid and reads back as `null`, distinct from `0`.
- Negative costs are rejected with a field error.
- Dedup behaviour is unchanged.
- Full gates green; migration applies cleanly and idempotently.

## Outcome

- **Actual files:** as planned, plus one the plan missed —
  `src/scoreboard/routes/leaderboard.py`. `RankedLeaderboardEntry` there mirrors
  `LeaderboardEntry` field-for-field plus `rank`, and both set `extra="forbid"`, so adding the
  field to the schema alone produced a **500 on the read path** rather than a type error. Found by
  driving the live endpoint, not by the type checker. Left an `AIDEV-NOTE` on the class.
  Also `src/scoreboard/scores/migrations/0004_add_run_cost_usd.py`.
- **Gates:** `run_gates.py scoreboard --base origin/main` → append-only ✓, ruff check ✓,
  ruff format ✓, pyright ✓, pytest --cov ✓ (77 passed, 2 skipped in `tests/unit/scores/`).
  ALL GATES GREEN.
- **Verification (live, via the running app):**
  - a cost round-trips at full precision — `"12.345678"`, no float drift;
  - an omitted cost reads back `None`, **not** `0` (the D5 invariant);
  - an explicit `"0"` reads back `"0"` and stays distinct from `None`;
  - a negative cost is rejected `422`;
  - all three states appear correctly on `GET /v1/leaderboard/{id}`;
  - the migration applies from an empty database and is a no-op on re-run.
- **Deviations:**
  1. **The generated migration failed `ruff check` (`I001`, unsorted imports).** The gate caught it;
     fixed with `ruff check --fix` + `ruff format` on the generated file rather than by relaxing the
     gate, and re-verified that it still applies from scratch afterwards. Worth knowing that
     `tortoise makemigrations` output does not satisfy this repo's lint settings as emitted.
  2. **`RankedLeaderboardEntry` duplication** — see Actual files. This is a latent trap for any
     future field: the two classes must be edited together, and the failure mode is a runtime 500,
     not a static error.
  3. Frontier maths still not written — it belongs in `portal/leaderboard-logic.js`, which exists
     only on the unmerged `OME-769` branch (PR #569). Unchanged from D9.
  4. Pass 2 (Cost column, frontier marks, chart, cheapest-run stat) remains blocked on a client
     actually emitting a run total. Nobody is named for that yet — the open question on `OME-772`.
