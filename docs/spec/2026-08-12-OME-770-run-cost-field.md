# OME-770 (pass 1 of 2) — A run cost on a submission

Status: approved (owner, 2026-08-12) · Stack: scoreboard

**Written retroactively (2026-08-13).** The decisions below were all taken and owner-confirmed
interactively on 2026-08-12 and recorded as D1–D11 in
`docs/work/2026-08-12-OME-770-run-cost-field.md`; this file lifts them into the spec slot the
SDLC requires. It documents what was decided, not a redesign. See the ledger's Deviations.

## 1. Problem

`OME-770` asks for a Cost column, Pareto-frontier winner marks, and a cost-vs-accuracy chart —
three views over one number. None of them is buildable, because **that number does not reach
Scoreboard at all**. Nothing cost-shaped exists on `ScoreSubmission`, on the `Score` model, or on
`LeaderboardEntry`; there is no column to render, no value to compute a frontier over, and no
axis for the chart.

The upstream chain that would produce it has four links and Scoreboard owns only the last:

| # | Link | Owner | State |
|---|---|---|---|
| 1 | A provider call's cost is captured | aigateway | `OME-303` unmerged |
| 2 | Per-call costs roll up into a run total | Engine | not built |
| 3 | The Client sends that total on publish | Client | no field for it |
| 4 | **Scoreboard accepts, stores and exposes it** | **scoreboard** | **this unit** |

Waiting for 1–3 would leave `OME-770` blocked with no Scoreboard-side progress at all. Building
link 4 first inverts that: the moment a client can produce a total, it has somewhere to send it,
and `OME-770`'s remainder collapses to pure rendering.

## 2. Contract

A submission MAY carry a run cost. The field is `run_cost_usd` — the unit is in the name so no
reader has to infer it (D1).

| Property | Value | Why |
|---|---|---|
| Type | `Decimal`, **not** `float` | This is money; binary floating point cannot represent it exactly, and a published dollar figure must not accumulate representation error. `accuracy` stays a `FloatField` — a ratio is not currency. (D2) |
| Precision | `DECIMAL(12, 6)` | Both ends of the real range must fit: a cache-served smoke run costs fractions of a cent (`0.000123`), and a full DRACO rerun was quoted at $3–4k. `0.000001` → `999999.999999` covers both. (D2) |
| Nullability | `null=True`, no backfill | The column lands on an already-populated table, and `OME-770` itself specifies `n/a for imported/unknown` — absent is a *specified* state, not missing data. (D3) |
| Lower bound | `ge=0` | A negative run cost is not a thing. |
| Upper bound | `max_digits=12, decimal_places=6` on the request DTO | The request contract mirrors the column exactly. See §2.2. |

### 2.1 INVARIANT — absent is not zero

`None` means **no cost was reported**. `0` means **this run cost nothing**, which is a legitimate
and deliberately-pursued outcome: a fully cache-served run is `OME-767`'s zero-cost goal.

Conflating them is not cosmetic — it corrupts the feature that motivated the field. A Pareto
frontier ranks by cost ascending, so an unknown-cost row coerced to `0` becomes *the cheapest
entry on the board* and lands on the frontier for free. Every reader, renderer and frontier
computation must keep the two distinct: `None` is excluded from the frontier and rendered in a
gutter, never plotted at `$0`. (D5)

### 2.2 The bounds are part of the contract, not just the column

`ge=0` alone is insufficient. Three failures were reproduced live against the running app with
only `ge=0` in place:

| Input | With `ge=0` only | Why that is wrong |
|---|---|---|
| `0.0000009` | `201`, stored as `0.000001` | Publishes a figure the submitter never sent — silent alteration of money. |
| `1000000` | `201` on SQLite | Seven integer digits overflow `DECIMAL(12, 6)`; passes locally, fails on Postgres. A backend-dependent contract is not a contract. |
| `1e30` | `500` | An input-validation failure surfacing as a server error. |

Mirroring the column's `max_digits`/`decimal_places` on `ScoreSubmission` turns all three into a
`422` field error at the edge. **A value that cannot be stored exactly must be rejected, never
rounded** — the alternative is publishing a number nobody submitted.

### 2.3 Trust model — self-reported, and labelled as such

A run cost is **materially harder to verify than accuracy**. Re-running a submission tells us what
*we* paid, not what the submitter paid, so a submitter who understates cost lands on the
cost-efficiency frontier at no risk of being caught by reproduction.

The decision is therefore: **store it, expose it, and mark its provenance in the UI** — never
present it as verified. The frontier is computed over self-reported numbers and the UI must say
so, reusing the verified/unverified distinction the board already carries for accuracy (the
mechanism `OME-771`'s Status column provides). (D11)

## 3. `content_hash` is deliberately NOT extended

The dedup hash covers **recipe identity** — benchmark, spec, url4 expression, result numbers,
provider order — and deliberately excludes client-supplied context. Cost is a property of *one
execution* of a recipe, not of the recipe: two runs of the same recipe can legitimately cost
different amounts and must still collapse to a single row. Adding cost to the hash would silently
break `OME-391`'s dedup guarantee. (D7)

### 3.1 Accepted consequence

Because of §3, a recipe already submitted **without** a cost cannot later gain one. Verified in
`store.py` — a dedup hit returns the stored row and never writes the incoming data — so the two
directions are asymmetric:

- **(A)** first submission carries a cost → later identical ones read it back. Fine.
- **(B)** first carries none → a later cost is **silently discarded**; the client gets
  `created=False`, a null cost, and no signal that its value was dropped.

**Owner decision:** accept (B) and do **not** add a dedup fill-in — `OME-391`'s immutability is
worth more than retrofitting cost onto historical rows. §4 removes case (B) for new recipes
anyway. (D8)

## 4. Optional now, required later

Owner direction: *"we should work towards rejecting if cost is missing even on the first run after
it is available."* Once the Client can emit a total, a direct submission without one is a client
bug, not a legitimate state.

It cannot be required **now**, for three independent reasons:

1. **Nothing sends it.** A required field would reject *every* submission — including the
   documented smoke test and the verified `cloudflared` path.
2. **`NOT NULL` cannot be added** to the already-populated table without inventing a cost for
   existing rows.
3. **`OME-770` specifies `n/a for imported/unknown`**, which imported `OME-322` baselines
   legitimately are.

Target end state: **required on direct submissions, `null` only for imported/legacy rows.** (D10)

## 5. Scope boundary — backend only

The frontier maths belongs in `portal/leaderboard-logic.js`, which exists only on the unmerged
`OME-769` branch (PR #569). Writing it here would recreate a file already under review and
guarantee a conflict. It follows once #569 lands. (D9)

Pass 2 — Cost column, frontier marks, chart, cheapest-run stat — additionally remains blocked on
a client actually emitting a run total (§1, links 1–3). Nobody is named for that yet; it is the
open question on `OME-772`.

A display constraint belongs to pass 2 and is recorded here so it is not lost between passes:
**full precision is stored, but the UI must round for display**, so a six-decimal figure cannot
overflow the Cost column's width. (D2)

## 6. Acceptance

- A client can submit `run_cost_usd`; it persists and appears on `GET /v1/leaderboard/{id}` and on
  the per-spec history.
- Omitting it is valid and reads back as `null`, distinct from `0`.
- A negative cost, an over-precise cost, and an over-large cost are each rejected with a field
  error — never rounded, never backend-dependent, never a `500`.
- Dedup behaviour is unchanged.
- Full gates green; the migration applies cleanly and idempotently.
