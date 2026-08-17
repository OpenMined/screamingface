# OME-820 — Implementation plan

Spec: `docs/spec/2026-08-13-OME-820-default-verified.md` · Ledger:
`docs/work/2026-08-13-OME-820-default-verified.md`

One SDLC unit, one stack (`scoreboard`), backend only. RED before GREEN at every step. The field is
already carried end to end through the store, all read DTOs and the portal, so only its **default**
and its **documented meaning** move — no plumbing.

## Step 1 — RED: the three behaviours

`apps/scoreboard/tests/unit/scores/test_schemas.py`:

- a `ScoreSubmission` that **sends** `verified_by_openmined` (both `true` and `false`) raises
  `ValidationError`. This is the D4 integrity invariant, and it should already pass via
  `extra="forbid"` — write it anyway, because the value of the test is that it fails loudly if
  someone ever relaxes the config.

`apps/scoreboard/tests/unit/scores/test_store.py`:

- a submission omitting the field is stored `verified_by_openmined is True` (**fails today**);
- a row explicitly created `False` still reads `False` after the change — the no-backfill guarantee
  (D5). Passing before and after, and that is the point: it pins that the default applies to new
  rows only;
- `mark_verified()` on an already-verified row leaves it `True` (idempotence regression).

`apps/scoreboard/tests/unit/test_leaderboard_routes.py`:

- a submission omitting the field reads `true` on `GET /v1/leaderboard/{id}` **and** the per-spec
  history (**fails today**).

## Step 2 — GREEN: the default

`src/scoreboard/scores/models/score.py`:

```python
verified_by_openmined = fields.BooleanField(default=True)
```

Anchors required, since a bare `True` here is the opposite of what a reader expects on a trust flag:
`WHY` recording that verified means *executed on OpenMined infrastructure* (spec §2.1), and
`INVARIANT` recording that it is **never** client-settable (spec §3) with a pointer to `OME-821`
for when the default stops being true.

## Step 3 — the migration (stack rule S1, same iteration)

```sh
uv run tortoise makemigrations --name default_verified_true
uv run tortoise migrate
```

Tortoise 1.1.7 built-in CLI, **never Aerich**; config resolves from `[tool.tortoise]` in
`pyproject.toml`, so no `-c` flag.

Two things to verify explicitly rather than assume:

1. **Whether a default change even produces a migration.** A Tortoise `default=` is applied in
   Python on instantiation, not necessarily as a DB-level `DEFAULT` clause. If `makemigrations`
   reports no changes, that is the correct outcome and must be recorded in the ledger — not worked
   around by hand-writing one.
2. **Existing rows must be untouched.** Whatever is generated, it must not carry an `UPDATE`. If the
   generator emits a backfill, remove it — D5 is deliberate.

Expect `ruff check` to flag the generated file (`I001` hit the last generated migration on
`OME-770`); fix the file, never the gate.

## Step 4 — GREEN: correct the documentation that now lies

`src/scoreboard/routes/scores.py` states the opposite of the new behaviour in two places:

- the module docstring: *"The verified_by_openmined response field is a separate, independent
  trust-tier signal — submitted scores default to unverified regardless of how the submitter
  authenticated."* The first clause stays true and matters (it is independent of authentication);
  the "default to unverified" claim is now false.
- `get_score`: *"inspect verified_by_openmined before trusting it"* — still sound advice, but it
  should say what the flag now asserts.

## Step 5 — gates and close

`uv run .claude/scripts/run_gates.py scoreboard --base origin/main` — all green. Then a live probe:
submit with no verified field against a freshly migrated database and confirm `true` on all three
read paths, plus a pre-existing `False` row still reading `false`. Fill the ledger Outcome, commit
with `Refs: OME-820`, open the PR.

## Risks

- **The default becomes wrong when local packaging ships** (spec §4), which was reported at the same
  huddle as landing by EOD. `OME-821` is filed and linked blocked-by so the dependency is visible;
  the PR body must say so too, because a reviewer approving this needs to know it has an expiry
  condition.
- **`makemigrations` may legitimately produce nothing** (step 3). Recording that is part of the
  unit, since a future reader will otherwise wonder why a schema-ish change has no migration.
