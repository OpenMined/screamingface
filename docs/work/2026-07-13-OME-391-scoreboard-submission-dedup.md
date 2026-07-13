---
ticket: OME-391
stack: scoreboard
status: done
started: 2026-07-13
finished: 2026-07-13
---

# OME-391 (step 1 of 2) — server-enforced dedup by recipe content hash

## Intent

C28: duplicate score submissions are only deduplicated when the client supplies an
optional `Idempotency-Key` header — identical no-header submissions currently create
duplicate rows and pollute a spec's submission history. Make dedup server-enforced,
independent of any client-supplied header, by hashing the submission's "recipe"
(what was actually run and its result), not who submitted it or when.

Step 2 of OME-391 (write-path authentication/attribution, C2) is explicitly deferred —
posted on the ticket as blocked on a product decision + a dependency on OME-326
(OpenMined identity provider, not yet built). Not touched in this unit.

## Planned changes

- `apps/scoreboard/src/scoreboard/scores/models/score.py`: add `content_hash`
  (`CharField(64)`, unique) to `BaseScore`. Migration in the same iteration (rule S1).
- `apps/scoreboard/src/scoreboard/scores/store.py`: new `_content_hash(submission)` —
  sha256 hex over `benchmark_id, spec_id, url4_expression, accuracy, total_questions,
  correct_questions, ran_with_providers` (in submitted order — provider order is part
  of recipe identity, not sorted away). `ScoreStore.submit`: after the existing
  idempotency-key fast path, look up by `content_hash` before creating; on a hit,
  return the existing score (same 200-with-existing-row semantics idempotency already
  uses). Extend the existing `IntegrityError` race handler to also re-query by
  `content_hash` (mirrors the existing idempotency-key race-handling pattern).
- `apps/scoreboard/src/scoreboard/routes/scores.py`: no route-level change expected —
  dedup stays inside the store; confirm during implementation.

## Test plan

- Two submissions with identical recipe fields but no `Idempotency-Key` header →
  second call returns 200 with the *same* score id as the first (not a new 201 row).
- Two submissions with identical recipe fields but different `submitted_by` /
  `client_*` / `ran_at_local` → still treated as the same recipe (still deduped) —
  proves the hash is over recipe identity, not the whole row.
- Two submissions with different `ran_with_providers` order → NOT deduped (treated as
  distinct) — proves order is preserved, not sorted away.
- A genuinely different submission (different accuracy) → not deduped, creates a new
  row (regression: normal submission still works).
- Concurrent-race safety net: simulate the `IntegrityError` path directly (mirrors the
  existing idempotency race test) and confirm it resolves to the existing row instead
  of raising.
- Migration applies cleanly; second run is a no-op (existing repo convention).

## Acceptance

- Identical-recipe submissions without a header no longer create duplicate rows.
- All prior tests remain green and unmodified.
- `run_gates.py scoreboard --skip-append-only` all green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `apps/scoreboard/src/scoreboard/scores/models/score.py` — added `content_hash`
    (`CharField(64)`, `unique=True`, `null=True` — nullable so the column can be added
    to a table with existing rows without a backfill).
  - `apps/scoreboard/src/scoreboard/scores/migrations/0003_auto_20260713_1505.py` —
    new migration; verified against a scratch DB seeded with pre-existing rows
    (clean apply, second run is a no-op).
  - `apps/scoreboard/src/scoreboard/scores/store.py` — `_content_hash()`;
    `ScoreStore._resolve_existing()` (shared helper for the pre-insert check and the
    `IntegrityError` race handler — added during the complexity-gate pass to bring
    `submit()` back under `PLR0911`/`PLR0912`); `ScoreStore.find_existing()` (public,
    added during self-review to replace two separate route-level lookups —
    `get_by_idempotency_key` + a since-removed `get_by_content_hash` — with one call
    that reuses `_resolve_existing` and computes the content hash once instead of
    per-lookup); `_submission_to_kwargs()` now takes the already-computed
    `content_hash` instead of recomputing it a third time on the insert path.
  - `apps/scoreboard/src/scoreboard/routes/scores.py` — route-level pre-check via
    `find_existing()` so a dedup hit answers 200, not 201. Deviation from plan: the
    plan expected no route change; this was required once testing showed the route
    didn't know `store.submit()` had resolved to an existing row internally.
  - `apps/scoreboard/tests/unit/scores/test_store.py` — 6 new tests (5 dedup cases,
    including one added during self-review for sequential different-idempotency-keys
    same-recipe dedup, + 1 Postgres concurrent-race test).
  - `apps/scoreboard/tests/unit/test_scores_routes.py` — 2 prior tests modified with
    explicit user sign-off (see Deviations).
- **Commits:** this unit's commit (see `git log` on this file's introducing commit;
  `Refs: OME-391`).
- **Gates:** `run_gates.py scoreboard --skip-append-only` — ALL GATES GREEN (ruff
  check, ruff format --check, pyright, pytest). 117 passed, 2 skipped, 88.01% coverage.
- **Deviations:**
  - Acceptance criterion "all prior tests remain green and unmodified" was not fully
    met: `test_post_score_without_idempotency_key_always_creates_new_row` and
    `test_post_score_with_expired_idempotency_key_creates_new_row` asserted the exact
    behavior this ticket fixes (no-header duplicates create new rows). Both were
    rewritten with explicit user sign-off — the first to assert the new dedup
    behavior (renamed to `..._dedupes_identical_recipe`), the second to use a
    genuinely different recipe under the same expired key so it still tests what it
    originally intended (key expiry) without colliding with the new content-hash
    guard.
  - Route-level change not anticipated in the plan (see above).
  - `ScoreStore.submit()` initially exceeded `PLR0911`/`PLR0912`; resolved via
    `_resolve_existing()` extraction rather than bumping the threshold, per
    `docs/complexity-baseline.md` convention.
  - Self-review (3 rounds) after the initial commit found: (1) redundant
    content-hash computation/lookups across the route pre-check and `submit()`'s own
    internal pre-check — partially addressed via `find_existing()` and threading the
    hash through `_submission_to_kwargs`; the remaining route-vs-`submit()` double
    pre-check on the genuinely-new-submission path was deliberately left as-is rather
    than changing `submit()`'s return contract to a `(schema, created)` tuple, since
    that would ripple through ~30 existing call sites for a sub-millisecond gain —
    disproportionate to the task; (2) added an explicit test for the sequential
    different-idempotency-keys-same-recipe scenario (the core C28 case) instead of
    relying on it being implied by the no-header tests; (3) documented (comment only)
    that `version` is excluded from the hash as currently a no-op since
    `ScoreSubmission.version` is pinned to `Literal[1]` — revisit if that changes.
