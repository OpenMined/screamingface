# OME-820 — What "verified" means on the leaderboard

Status: approved (owner, 2026-08-13) · Stack: scoreboard

## 1. Problem

`verified_by_openmined` is the board's trust signal. Today it is **unreachable**:

| Fact | Consequence |
|---|---|
| `BooleanField(default=False)` | every new row starts unverified |
| No HTTP route sets it — only `store.mark_verified()`, which nothing calls | no row can ever *become* verified |
| `OME-414` (re-run verification service) is in Backlog, unstaffed, no compute budget | nothing will call it soon |

So the board displays "unverified" on every row, permanently. `OME-769`'s board renders that flag
in a Verified column, and `OME-771` is meant to build a Reproducible/All toggle on top of it — a
toggle whose "Reproducible" pool would always be empty.

Ahead of Monday's tester cohort, a board where nothing is ever verified reads as broken rather than
cautious. The 2026-08-13 huddle asked for the default to flip.

## 2. The real question

Flipping a boolean is one character. The question is **what the flag then claims**, because the
claim is published on a public leaderboard whose entire pitch is that it is verified.

The field's documented meaning is "OpenMined independently reproduced this run on shared compute"
(`OME-771`). Defaulting *that* to true would publish a reproduction that never happened.

### 2.1 The decision

**Verified means: this run executed on OpenMined infrastructure.**

For the Monday cohort this is literally true. Testers run against the hosted SF Engine, through
OpenMined's AI Gateway, on OpenMined's capped keys. The numbers were produced by our compute, so
there is nothing to independently reproduce — the claim is not weaker than "reproduced", it is a
*different and directly verifiable* claim.

### 2.2 Alternatives rejected

| Alternative | Why rejected |
|---|---|
| Flip the default, keep the "we reproduced this" meaning | The database would assert a reproduction that did not occur. Worse, once `OME-414` exists, a defaulted row becomes **indistinguishable** from a genuinely reproduced one — the corruption is permanent and silent. |
| Leave storage `False`, hide the distinction in the UI | The API would return `false` while the board implied verified. Two sources of truth disagreeing, and `OME-771` inherits the contradiction. |

## 3. Contract

- `verified_by_openmined` defaults to **`True`** for new rows.
- It is **absent from `ScoreSubmission`** and stays absent. A submitter must never be able to
  declare its own trust tier; `extra="forbid"` turns an attempt into a `422`.

  **INVARIANT.** This is the load-bearing one. If a client could set this field, the board's trust
  signal would be self-asserted by the very party it is meant to constrain — and the write path is
  public (authenticated, but public). It is pinned by an explicit test rather than left to the
  model config.
- Existing rows are **not backfilled** and keep `False`. Some of them are local test submissions
  that genuinely did not run on OpenMined infrastructure, so backfilling would assert a falsehood.
  Showing specific historical rows as verified is a deliberate data operation, not a schema default.
- `store.mark_verified()` keeps working unchanged. Under the new meaning it is redundant for hosted
  runs, but it remains the mechanism `OME-414` will use, and it stays idempotent.

## 4. When this default becomes wrong

The default is honest **only while every execution path is ours.** It stops being honest the moment
a run happens elsewhere:

- **BYOK** — the user supplies their own provider keys.
- **Local / packaged execution** — the CLI or desktop app running the stack on the user's machine
  (`OME-678`; Tauquir's packaging, PR #559, was reported at the same huddle as landing by EOD).

Those runs are **self-reported**, and defaulting them to verified would publish a claim OpenMined
cannot stand behind.

This is `OME-821`, filed and linked as blocked by this ticket. Two things there are deliberately
left open for the owner rather than assumed here:

- `client_name` / `client_version` / `client_platform` already exist on a submission but are
  **client-declared and trivially forgeable** — they cannot by themselves carry a trust tier.
- `OME-414` states "no unverified score may ever rank". That predates this split, and whether a
  self-reported run may rank at all needs reconciling.

**The risk to name plainly:** local packaging is expected within days. If it ships before `OME-821`,
this default silently starts publishing false verification claims. The linkage exists so that is a
visible dependency rather than a discovered one.

## 5. Acceptance

- A submission omitting the field reads back `verified_by_openmined: true` on
  `GET /v1/leaderboard/{id}`, the per-spec history, and `GET /v1/scores/{id}`.
- A submission sending the field is rejected with a field error.
- Rows created before this change still read `false`.
- `store.mark_verified()` remains correct and idempotent.
- Full gates green; the migration applies cleanly and idempotently, with no model drift afterwards.
