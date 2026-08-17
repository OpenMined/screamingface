---
ticket: OME-865
stack: scoreboard
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-865 — Rename the Scoreboard verification field to verified_by_screamingface

## Intent

`OME-858` (#622, merged 14:42) renamed the field to `verified_by_screamingface` in the Client and
made its decoder strict. Scoreboard still emits `verified_by_openmined`, so the two no longer
agree and every read path fails.

**Reproduced against `origin/main` before starting**, not inferred from the ticket:

```
sf.leaderboards.get('draco')
→ LeaderboardError: Invalid Scoreboard Leaderboard response:
  Leaderboard entry verified_by_screamingface must be a boolean
```

This blocks `OME-402` (the leaderboard notebook, the path testers submit through) and any Client
↔ Scoreboard end-to-end run. The ticket is scoped by Keelan; this ledger records only what the
ticket does not already decide.

## Scale

18 files, ~30 occurrences on `origin/main`: model, schemas, routes, store projections, four portal
JS files, eight test modules, and `0001_initial.py`.

## Decisions

**D1 — data-preserving `RenameField`, not a DB reset.** The ticket allows either. `ops.RenameField`
exists in this Tortoise version (verified by introspection, signature
`(model_name, old_name, new_name)`), so the preserving option is available and strictly safer:
the dev database keeps its rows and nothing has to be reseeded. A reset would be chosen only if
no preserving path existed.

**D2 — `0001_initial.py` is NOT edited.** It records history and has already been applied
everywhere. The rename goes on top as a new migration. Editing an applied migration would
desynchronise every existing database from its recorded history.

**D3 — the new migration is `0005`, depending on BOTH `0004`s.** `main` currently carries two
sibling `0004` migrations (`_20260806_0000` from `OME-323`, `_20260816_0630` from `OME-775`), each
declaring `0003` as parent — a branched history with no convergence point. Depending on both
merges the branch, so a future `0006` has one unambiguous parent. This is a free fix for a latent
hazard noticed during `OME-775`'s smoke testing.

**D4 — semantics are untouched.** This renames a key. It must not introduce a badge, filter,
ranking rule or reproduction claim; `OME-820` removed those deliberately and `OME-821` owns
restoring them once the field means something. The field also stays server-owned and absent from
`ScoreSubmission`, which a test already pins.

## Planned changes

- `scores/models/score.py`, `scores/schemas.py`, `scores/store.py`, `routes/leaderboard.py`,
  `routes/scores.py`
- `portal/{benchmark,leaderboard-logic,main,spec}.js`
- `scores/migrations/0005_*.py` — new, `RenameField` + convergent dependencies
- tests: `test_schemas`, `test_store`, `test_frontier`, `test_openness`, `test_leaderboard_routes`,
  `test_scores_routes`, `test_sf_payload`, `tests/portal/leaderboard-logic.test.js`

## Test plan

The existing suite already pins this field's behaviour throughout, so the rename is verified by
those tests continuing to pass under the new name rather than by new ones. The contract itself is
verified end to end: the real Client against a real Scoreboard, which is the check that currently
fails and must pass.

## Acceptance

- No Scoreboard response emits `verified_by_openmined`.
- A submission setting the server-owned field is still rejected.
- `sf.leaderboards.list/get/submit/get_score` all succeed against a local Scoreboard.
- Existing rows survive the migration with their values intact.
- Full gates green.

## Outcome

- **Actual files:** as planned — 17 files renamed (45 occurrences), plus the new
  `0005_auto_20260817_1520.py`. `0001_initial.py` deliberately untouched (D2). One extra file
  beyond the ticket's list: `portal/portal.css`, which mentioned the field in a comment.
- **Gates:** ruff check ✓ · ruff format ✓ · pyright ✓ · pytest --cov ✓ **253 passed, 2 skipped**
  · portal JS 14 passed. `makemigrations` → **"No changes detected"** (no model/migration drift).
  Ran with `--skip-append-only`: a rename cannot avoid touching prior tests. Owner-approved under
  rule 5 after I demonstrated the diff is purely the identifier — every changed line is identical
  once the field name is normalised.

### Verification beyond the unit suite

The two things the suite cannot cover were each proven directly:

1. **Data survives the rename.** Built the schema at `0004` with `0005` held back, inserted two
   rows through raw SQL (`old-row` false, `new-row` true), then applied `0005`. Both read back
   with their original values under the new column, and the old column is gone. This is the
   `OME-820` D5 invariant — a drop-and-recreate would have defaulted `old-row` to true and
   published a claim about a run nobody checked.
2. **The contract is repaired.** The real `sf.Client` against a real Scoreboard:
   `list()` ✓ · `submit()` ✓ · `get()` ✓ · `get_score()` ✓ — all four failed on `origin/main`
   before this. No response emits the old key on any of the three read endpoints, and a
   submission claiming the server-owned field is still rejected **422**.

### Deviations

1. **The migration-backfill guard was hardened, not just renamed.**
   `test_no_migration_backfills_the_verified_column` scans *migration sources* for the field name.
   A blind rename would have left it checking only the new name, while every pre-rename migration
   carries the old one — so it would have gone blind on half the history. It now checks both.
   Found by reading the test rather than trusting the rename; a mechanical sed would have silently
   degraded it.
2. **`0005` declares two parents.** `main` carried two sibling `0004` migrations, both claiming
   `0003`, from `OME-323` and `OME-775` merging minutes apart. Depending on both converges that
   branch so the next migration has one unambiguous parent. Free fix for a latent hazard noticed
   during `OME-775`'s smoke testing; not requested by the ticket.
3. **`portal/portal.css` was in scope after all** — the ticket listed "portal code" and the field
   appeared in a CSS comment explaining the withdrawn stat.
