---
ticket: OME-852
stack: scoreboard
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-852 — Repair main: test helpers omit the required benchmark_revision

## Intent

`origin/main` is red — 9 failing tests and 2 pyright errors in `apps/scoreboard`. Restore it
without weakening the guarantee that caused the break.

## Cause

A semantic conflict git cannot detect. Two PRs merged three minutes apart, each green alone:

| commit | time | change |
|---|---|---|
| `62a0735d` | 14:22 | `OME-323` / #519 — frontier + openness tests building `ScoreSchema` |
| `e431b715` | 14:25 | `OME-775` / #611 — made `benchmark_revision` **required** on `ScoreSchema` |

Neither branch contained the other, so neither CI run saw the combination. No textual conflict
existed for git to report. Both PRs were legitimately green at merge time.

## Blast radius — test-only

Production is unaffected. The one production construction site, `store.py:353`
(`LeaderboardEntry(**row)`), takes the column straight from the query and is correct.

All 9 failures trace to **two shared test helpers**, not 9 independent call sites:

- `tests/unit/scores/test_frontier.py` `_score()` — 6 failures
- `tests/unit/classification/test_openness.py` `_score()` — 3 failures

## Decision (owner, 2026-08-17)

Pass `benchmark_revision=None` explicitly in both helpers. **The field stays required.**

**Rejected: defaulting the field to `None`.** One line, no test edits, fastest to green — but a
site that forgets the revision would then silently receive `None`, which since `OME-775` means
*"excluded from every registered board"* rather than a loud type error. That silent-exclusion
failure mode is exactly what `OME-775` was fixed to prevent, so the loudness is load-bearing.

`None` is honest in these two helpers: frontier and openness classification genuinely do not
depend on benchmark revision.

**Rule 5:** this edits prior tests. Owner approved 2026-08-17.

## Planned changes

- `apps/scoreboard/tests/unit/scores/test_frontier.py` — `benchmark_revision=None` in `_score()`
- `apps/scoreboard/tests/unit/classification/test_openness.py` — same in `_score()`

## Test plan

No new tests. This restores 9 existing ones. The guard is that the field stays required, which
`test_schemas.py` already pins and which pyright enforces at every construction site.

## Acceptance

- `pytest` green (was 9 failed, 214 passed).
- `pyright` clean (was 2 errors).
- `benchmark_revision` still required on `ScoreSchema`.
- Full gates green.

## Outcome

- **Actual files:** exactly as planned — the two `_score()` helpers. The `BaselineSchema`
  helpers in the same files were checked and correctly left alone; baselines carry no
  benchmark revision.
- **Gates:** ruff check ✓ · ruff format ✓ · pyright ✓ (was 2 errors) · pytest --cov ✓
  **223 passed, 2 skipped** (was 9 failed, 214 passed) · portal JS 14 passed.
  Ran with `--skip-append-only`: the whole point of this unit is editing two prior test
  helpers, owner-approved under rule 5 and recorded in the ticket.
- **Deviations:** none. Two helpers rather than the 9 call sites first estimated — the
  failures were all downstream of two shared constructions.
